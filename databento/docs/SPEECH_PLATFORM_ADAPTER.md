# Platform Adapter — Resumen Detallado de Trabajo Realizado

**Fecha:** Febrero 2026  
**Proyecto:** Platform Adapter para Interactive Brokers TWS/Gateway  
**Cliente:** Pete Davis  
**Estado:** ✅ Completado y en producción  
**Versión actual:** 2.0 (r2)

---

## 1. Contexto y punto de partida

Antes de empezar este proyecto, no existía ningún puente entre nuestro sistema de trading algorítmico y el broker Interactive Brokers. Para poder enviar una orden, suscribirse a precios en tiempo real, o monitorear posiciones abiertas, había que interactuar directamente con la API oficial de IB (ibapi), que es una librería de bajo nivel: verbosa, sin tipos, con callbacks confusos, y sin ningún mecanismo de reconexión ni protección ante errores de red.

La idea del Platform Adapter fue crear esa capa intermedia — un módulo limpio y bien probado que hable con IB por abajo y exponga una interfaz ordenada hacia arriba, de modo que el resto del sistema (estrategias, ejecución, monitoreo de riesgo) nunca necesite saber nada sobre los detalles de la API del broker.

---

## 2. ¿Qué es el Platform Adapter exactamente?

El Platform Adapter (PA) es el módulo de software que conecta nuestro sistema de trading algorítmico con Interactive Brokers. Tiene dos responsabilidades y solo dos:

**Hacia abajo (PA → IB):** Recibir instrucciones del sistema de ejecución de órdenes (OE) — cosas como "compra 100 acciones de SPY a mercado" o "cancela la orden #47" — y traducirlas al formato exacto que exige la API de IB.

**Hacia arriba (IB → PA → sistema):** Tomar todo lo que IB nos manda — confirmaciones de órdenes, fills, cambios de posición, cotizaciones, estado de cuenta, errores — y reempaquetarlo como eventos limpios y tipados que el resto del sistema puede consumir sin fricción.

Lo que el PA no hace es igual de importante: no toma decisiones de trading, no calcula P&L, no guarda estado propio de negocio, no tiene estrategia. Es un traductor, no un cerebro. Esta separación es fundamental para que el sistema sea mantenible a largo plazo.

---

## 3. PA Versión 1 — MVP (completado el 27 de enero de 2026)

La primera versión fue construida en aproximadamente 4 días de trabajo intenso, del 23 al 27 de enero de 2026. El objetivo era tener algo completo, funcional y probado en vivo lo antes posible.

### 3.1 Gestión de conexión (`connection_manager.py` — 400 líneas)

Este es el componente más crítico del sistema. La API de IB opera sobre un socket TCP que puede caerse en cualquier momento — pérdida de red, reinicio del Gateway, sesiones expiradas. El ConnectionManager maneja todo eso de forma automática.

Lo que construimos:

- **Ciclo de vida completo:** conectar, desconectar, reconectar. La conexión se establece en menos de 1 segundo en condiciones normales.
- **Auto-reconexión con backoff exponencial:** si se pierde la conexión, el sistema espera 1s, luego 2s, luego 4s, etc., antes de reintentar. Esto evita saturar el Gateway con intentos de reconexión.
- **Hilo dedicado para mensajes:** la API de IB requiere un hilo que procese el message loop continuamente. El ConnectionManager lo gestiona de forma transparente con `threading.Thread(daemon=True)`.
- **Callbacks configurables:** el resto del sistema puede registrar callbacks para eventos de conexión/desconexión/error sin acoplarse al ConnectionManager.
- **Thread safety:** todos los accesos al estado de conexión están protegidos para evitar race conditions.

Se validó con 7 tests de integración: ciclo completo de conexión, reconexión simulada, múltiples clientes simultáneos, y manejo de fallos.

### 3.2 Streaming de market data (`market_data_adapter.py` — 450 líneas)

Este módulo se encarga de pedir y recibir datos de mercado desde IB. Hay dos tipos principales:

**Datos en tiempo real (streaming):** El adapter se suscribe a un símbolo y recibe un flujo continuo de ticks con bid, ask, last, volumen. Internamente usa el sistema de request IDs de IB para manejar múltiples suscripciones concurrentes sin que se mezclen.

**Datos históricos (on-demand):** Se puede pedir a IB el historial de barras OHLCV para cualquier símbolo, duración y tamaño de barra. La respuesta llega en callbacks asíncronos y el módulo los agrupa hasta el evento `historicalDataEnd` para entregarlos completos.

**Caché de quotes:** Los últimos quotes de cada símbolo se guardan en memoria para consulta inmediata, sin necesidad de pedir una nueva suscripción.

Se validó en vivo recibiendo 27 cotizaciones en tiempo real de 4 símbolos (AAPL, MSFT, TSLA, GOOGL).

### 3.3 Ejecución de órdenes (`order_execution_adapter.py` — 550 líneas)

El módulo más complejo. Maneja el ciclo de vida completo de cualquier orden desde que se crea hasta que se llena o cancela.

Tipos de órdenes soportados:
- **Market (MKT):** ejecución inmediata al mejor precio disponible
- **Limit (LMT):** se ejecuta solo si el precio llega al nivel especificado
- **Stop (STP):** se activa cuando el precio toca el nivel de stop
- **Stop-Limit (STP LMT):** combinación — stop activa la orden, límite controla el precio de ejecución
- **Bracket orders:** una orden de entrada más dos órdenes OCO (One-Cancels-Other) — stop loss y take profit. Cuando una se llena, la otra se cancela automáticamente.

Para cada orden se hace tracking completo: cuánto se llenó, cuánto queda, precio promedio de fill, comisiones. Los cambios de estado llegan como callbacks desde IB y el módulo los propaga al sistema.

Se validó con órdenes reales en cuenta paper, confirmando placement, fills y cancelaciones.

### 3.4 Gestión de cuenta (`account_manager.py` — 300 líneas)

Monitorea en tiempo real el estado financiero de la cuenta:

- **Balance y liquidez:** Net Liquidation, Available Funds, Buying Power, Cash Balance
- **Posiciones abiertas:** símbolo, cantidad, costo promedio, valor de mercado actual
- **P&L:** no realizado por posición y total de la cuenta
- **Valores de cuenta:** IB envía ~165 key-value pairs distintos en una actualización de cuenta. El AccountManager los captura todos y los expone de forma estructurada.

Se validó monitoreando una cuenta paper de $2,000 con 165 valores de cuenta en tiempo real.

### 3.5 Rate Limiter (`rate_limiter.py` — 153 líneas)

Interactive Brokers tiene límites de velocidad estrictos en su API. Si se exceden, IB desconecta al cliente y puede suspender la cuenta temporalmente. El rate limiter previene eso.

Implementado con el algoritmo **token bucket**: hay un cubo con tokens. Cada request consume un token. Los tokens se reponen a velocidad constante. Si no hay tokens, el request espera. Es más inteligente que un simple "X requests por segundo" porque permite ráfagas cortas dentro del límite.

Configurado para las operaciones más críticas: suscripciones de market data (50 por 10 minutos), historical data requests (60 por 10 minutos), y órdenes (45 por segundo).

22 tests unitarios verifican el comportamiento del rate limiter bajo carga.

### 3.6 Modelos de datos

Representaciones tipadas de las entidades del sistema:

- **`Contract`** — describe un instrumento financiero: símbolo, tipo (STK/FUT/OPT), exchange, moneda. Incluye conversión automática al formato de `ibapi.contract.Contract`.
- **`Order`** — estado completo de una orden: ID, símbolo, dirección, cantidad, tipo, precio, status, fills acumulados.
- **`Position`** — posición abierta: símbolo, cantidad (positiva = largo, negativa = corto), costo promedio.

Todos usan type hints completos. 15 tests unitarios cubren constructores, validaciones y conversiones.

### 3.7 Documentación del MVP

Se entregaron 4 documentos técnicos completos (~3,000 líneas en total):

- **README.md** (~800 líneas) — visión general, quickstart, ejemplos de código para cada componente, configuración, troubleshooting
- **API.md** (~600 líneas) — referencia completa de todas las clases y métodos con firmas, parámetros, tipos de retorno y ejemplos
- **USER_GUIDE.md** (~900 líneas) — tutoriales paso a paso, 10+ ejemplos avanzados, patrones como mean reversion y rebalanceo de portafolio, mejores prácticas
- **DEPLOYMENT.md** (~700 líneas) — checklist de producción, configuración de seguridad, monitoreo, backup, recovery, y patrones de deployment (single server, alta disponibilidad, microservicios)

### 3.8 Métricas del MVP

| Métrica | Valor |
|---|---|
| Líneas de código Python | ~6,100 |
| Archivos Python | 30+ |
| Tests unitarios | 37 (100% passing) |
| Tests de integración | 7 (100% passing) |
| Validación en vivo | ✅ exitosa |
| Documentación | ~3,000 líneas |
| Tiempo de desarrollo | 4 días (23–27 enero 2026) |

---

## 4. PA Versión 2 — Refactoring arquitectónico (r2)

Después de entregar el MVP, hicimos una revisión crítica del diseño antes de proceder a integrar el PA con el resto del sistema. Esta revisión encontró problemas importantes que, si no se corregían ahora, iban a generar bugs difíciles de rastrear en producción.

### 4.1 El problema: lógica de negocio infiltrada en el PA

La v1 tenía un componente llamado `StateManager` (497 líneas en `core/`). Su propósito original era guardar el estado del sistema en disco para poder recuperarse de reinicios. Pero con el tiempo había acumulado responsabilidades que no le correspondían:

- Guardaba un **cache local** de posiciones y órdenes, que podía desincronizarse con el broker
- Hacía **reconciliación automática** comparando su estado local con lo que IB reportaba, y tomaba acciones correctivas
- Calculaba **market value** y **P&L no realizado** de posiciones
- El `main.py` tenía `time.sleep()` después de mandar órdenes, esperando que el broker confirmara

Esto violaba el principio de diseño central del PA: ser un traductor puro, sin estado propio ni lógica de negocio. El cálculo de market value y P&L no realizado le corresponde al MIC (Market Intelligence Center). La reconciliación le corresponde al OE. El PA no debería estar haciendo ninguna de esas cosas.

El riesgo concreto: si el StateManager tiene posiciones que no coinciden exactamente con lo que IB tiene, el sistema puede pensar que está plano cuando en realidad tiene posición abierta, o puede mandar órdenes duplicadas creyendo que una orden anterior no se ejecutó.

### 4.2 La solución: contratos de interfaz formales

Lo primero que hicimos en r2 fue definir con precisión quirúrgica qué puede entrar y salir del PA. Esto quedó codificado en dos archivos en `src/platform_adapter/interfaces/`:

#### `pa_outputs.py` — lo que PA emite

PA solo puede emitir hechos del broker. Nunca datos derivados. Cada evento es un dataclass inmutable (`frozen=True`), lo que significa que nadie puede modificarlo después de crearlo — son snapshots del estado del broker en un momento específico.

Los 7 eventos definidos:

| Evento | Cuándo se emite | Campos clave |
|---|---|---|
| `QuoteEvent` | Tick en tiempo real del broker | symbol, timestamp, bid, ask, last, volume |
| `BarEvent` | Respuesta a pedido histórico | symbol, timestamp, O, H, L, C, volume, count, wap |
| `OrderUpdateEvent` | Cambio de estado de una orden | order_id, symbol, status, filled, remaining, avg_fill_price |
| `FillEvent` | Ejecución confirmada | order_id, exec_id, symbol, side, shares, price, commission |
| `PositionEvent` | Snapshot de posición | symbol, quantity, avg_cost, account |
| `AccountValueEvent` | Actualización de valor de cuenta | key, value, currency, account |
| `ConnectionEvent` | Conexión/desconexión/error | status, message |

Más los 4 eventos de control añadidos en r2:

| Evento r2 | Propósito |
|---|---|
| `KillStateEvent` | Notifica transición de estado kill (NORMAL → SOFTKILL → HARDKILL → LOCKOUT) |
| `FailsafeStageEvent` | Notifica escalada del monitor de heartbeat |
| `PacingStateEvent` | Notifica entrada/salida de pacing recovery por límites de IB |
| `ReconciliationReportEvent` | Resultado de reconciliación manual con el broker |

#### `pa_inputs.py` — lo que PA acepta

PA solo acepta comandos del OE. Nadie más puede mandarle instrucciones. Cada comando es también un dataclass inmutable con validación automática en `__post_init__`.

Los 7 comandos operacionales:

| Comando | Propósito | Validación automática |
|---|---|---|
| `PlaceOrderCommand` | Colocar una orden nueva | action ∈ {BUY,SELL}, qty > 0, LMT requiere limit_price, STP requiere stop_price |
| `CancelOrderCommand` | Cancelar orden existente | order_id requerido |
| `ModifyOrderCommand` | Modificar orden (precio/cantidad) | Al menos un campo a cambiar, qty > 0 |
| `FlattenCommand` | Cerrar toda posición en un símbolo | symbol requerido |
| `SubscribeMarketDataCommand` | Suscribirse a cotización en tiempo real | symbol requerido |
| `UnsubscribeMarketDataCommand` | Cancelar suscripción | symbol requerido |
| `HistoricalDataCommand` | Pedir barras históricas | symbol requerido, duration/bar_size con defaults sensatos |

Más los 7 comandos de control añadidos en r2:

| Comando r2 | Propósito |
|---|---|
| `SoftKillCommand` | Activar SoftKill: bloquea órdenes de apertura, permite reducir/cerrar |
| `HardKillCommand` | Activar HardKill: cancela todo, aplana posiciones, entra en LOCKOUT |
| `ResumeNormalCommand` | Volver a estado NORMAL desde SoftKill o FailsafeFreeze |
| `SetLockoutCommand` | Forzar LOCKOUT hasta reset manual |
| `HeartbeatCommand` | Señal de vida del OE — si deja de llegar, el failsafe escala |
| `ReconcileCommand` | Disparar reconciliación manual con el broker |
| `SwitchModeCommand` | Cambiar entre modo Live y Paper (reconecta en otro puerto) |

### 4.3 El sistema de kill states

Uno de los aportes más importantes de r2 fue diseñar e implementar un sistema de estados de seguridad para el PA. El problema original: si el OE (la capa de estrategia) tiene un bug y empieza a mandar órdenes en loop, o si hay una anomalía de mercado, necesitamos poder detener el sistema de forma ordenada y controlada, sin perder posiciones ni generar más exposición.

Los 4 estados posibles:

```
NORMAL → SOFTKILL → HARDKILL → LOCKOUT
```

- **NORMAL:** operación regular. Todo permitido.
- **SOFTKILL:** modo precautorio. Se bloquean nuevas aperturas de posición (órdenes BUY cuando se está plano, órdenes que agregan tamaño). Solo se permiten órdenes que reducen o cierran posición, y cancelaciones. Útil cuando hay señal de alarma pero no es urgente.
- **HARDKILL:** acción inmediata. PA cancela todas las órdenes pendientes, aplana todas las posiciones con órdenes de mercado, y entra en LOCKOUT. No hay vuelta atrás automática.
- **LOCKOUT:** estado terminal. Absolutamente ninguna orden puede pasar. Solo puede salirse con reset manual.

### 4.4 El failsafe de heartbeat

El sistema de heartbeat es una protección adicional: el OE debe enviar un `HeartbeatCommand` periódicamente para demostrar que sigue vivo y funcionando. Si el PA deja de recibir heartbeats, escala automáticamente:

- **Etapa 0 (NORMAL):** heartbeats llegando normalmente
- **Etapa 1 (WARN):** X segundos sin heartbeat → alerta, log de advertencia
- **Etapa 2 (FREEZE):** más tiempo sin heartbeat → bloquea nuevas órdenes (similar a SoftKill)
- **Etapa 3 (FLATTEN):** aún más tiempo → aplana posiciones automáticamente

Esto protege contra el escenario donde el OE se crashea pero el PA sigue conectado a IB con posiciones abiertas.

### 4.5 Pacing recovery

IB tiene un sistema de pacing que limita la velocidad de pedidos de datos históricos. Si se excede, IB devuelve el error code 162 ("Historical data request pacing violation"). Antes de r2, este error simplemente se logueaba y el sistema podía seguir pidiendo datos, acumulando violaciones hasta que IB desconectaba al cliente.

En r2 se implementó un módulo de pacing recovery: al detectar el error 162, el PA entra en modo recovery con un cooldown que aumenta exponencialmente con cada violación consecutiva. Durante el cooldown, todos los pedidos históricos se encolan y se van procesando a medida que el cooldown expira. El sistema vuelve a NORMAL automáticamente.

### 4.6 Cuarentena del StateManager

El `StateManager` (497 líneas), el módulo de `account.py` duplicado (código muerto), y el `main_v1.py` original fueron movidos a `src/platform_adapter/_quarantine/`. No se borraron — están ahí como referencia histórica — pero ya no son parte del sistema activo ni se importan desde ningún lado.

El `main.py` se reescribió de 587 líneas a ~380 líneas. Desaparecieron todos los `time.sleep()`, toda la lógica de reconciliación, y todo el cableado del StateManager.

### 4.7 Limpieza de modelos

En la v1, el modelo `Position` tenía dos métodos, `market_value()` y `unrealized_pnl()`, que devolvían `None` con un comentario de "TODO". Eso era código que prometía algo que no cumplía. En r2 esos métodos fueron eliminados. El PA no debe calcular market value ni P&L — eso es responsabilidad del MIC que consume los `PositionEvent` y `QuoteEvent` y hace los cálculos él mismo.

### 4.8 Tests en r2

La suite de tests se expandió de 44 a 122 tests. Los tests nuevos cubren:

- Todos los eventos de `pa_outputs.py`: construcción, inmutabilidad, validación de campos
- Todos los comandos de `pa_inputs.py`: construcción, validaciones de `__post_init__`, casos de error
- Los kill states: transiciones válidas e inválidas
- El failsafe: escalada por tiempo, reset por heartbeat
- El pacing recovery: detección de error 162, cooldown, cola de pedidos

---

## 5. Arquitectura completa — cómo fluye todo

```
┌─────────────────────────────────────────────────────────────┐
│                    OE / Strategy Layer                       │
│                                                             │
│   PlaceOrderCommand    CancelOrderCommand                   │
│   FlattenCommand       SoftKillCommand                      │
│   HeartbeatCommand     HistoricalDataCommand                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │  PAInputStream (Protocol)
                         │  handle_place_order()
                         │  handle_cancel_order()
                         │  set_softkill() / hardkill()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      PA 2.0 (main.py)                        │
│                                                             │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│   │ Kill States  │  │  Failsafe    │  │ Pacing Recovery  │ │
│   │ NORMAL       │  │  Heartbeat   │  │ Error 162        │ │
│   │ SOFTKILL     │  │  monitor     │  │ cooldown queue   │ │
│   │ HARDKILL     │  └──────────────┘  └──────────────────┘ │
│   │ LOCKOUT      │                                          │
│   └──────────────┘                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │  TCP socket (ibapi)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     IB Gateway / TWS                         │
│                                                             │
│   Puerto 7497 (Paper)      Puerto 7496 (Live)               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │  EWrapper callbacks
                         │  orderStatus(), execDetails()
                         │  tickPrice(), historicalData()
                         │  updatePortfolio(), updateAccountValue()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   PA Adapters (traducción)                   │
│                                                             │
│  MarketDataAdapter    OrderExecutionAdapter   AccountManager │
│  ConnectionManager    RateLimiter                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │  PAOutputStream
                         │  QuoteEvent, BarEvent
                         │  FillEvent, OrderUpdateEvent
                         │  PositionEvent, AccountValueEvent
                         │  KillStateEvent, FailsafeStageEvent
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              MIC / OE (downstream consumers)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Estructura de archivos

```
platform_adapter/
├── main.py                                  # PA 2.0 — thin pipe (~380 líneas)
├── src/platform_adapter/
│   ├── interfaces/                          # Contratos MIC (NUEVO en r2)
│   │   ├── pa_outputs.py                   # Eventos inmutables que PA emite
│   │   └── pa_inputs.py                    # Comandos que PA acepta
│   ├── core/
│   │   └── connection_manager.py           # TCP a IB, auto-reconexión (400 líneas)
│   ├── adapters/
│   │   ├── market_data_adapter.py          # Streaming + históricos (450 líneas)
│   │   ├── order_execution_adapter.py      # Ciclo de vida de órdenes (550 líneas)
│   │   └── account_manager.py             # Balance, posiciones, P&L (300 líneas)
│   ├── models/
│   │   ├── contract.py                     # DTO de instrumento (120 líneas)
│   │   ├── order.py                        # DTO de orden (180 líneas)
│   │   └── position.py                     # DTO de posición, sin stubs (100 líneas)
│   ├── utils/
│   │   ├── rate_limiter.py                 # Token bucket, thread-safe (153 líneas)
│   │   └── logger.py                       # Loguru setup (80 líneas)
│   ├── config/
│   │   └── settings.py                     # YAML config + .env
│   └── _quarantine/                        # Código removido del sistema activo
│       ├── state_manager.py                # (497 líneas — referencia histórica)
│       ├── account_model.py                # (código muerto — referencia)
│       └── main_v1.py                      # (PA 1.0 original — referencia)
├── tests/
│   ├── test_models.py                      # 15 tests: Contract, Order, Position
│   ├── test_utils.py                       # 22 tests: RateLimiter, Logger, Config
│   ├── test_interfaces.py                  # Tests de pa_outputs + pa_inputs (NUEVO)
│   └── test_integration_connection.py      # 7 tests de integración con IB
├── scripts/
│   ├── test_integration.py                 # 6 tests: conexión, cuenta, market data
│   └── test_live_trading.py                # Validación en vivo
├── docs/
│   ├── API.md                              # Referencia completa (~600 líneas)
│   ├── USER_GUIDE.md                       # Tutoriales y ejemplos (~900 líneas)
│   ├── DEPLOYMENT.md                       # Guía de producción (~700 líneas)
│   └── PA_2.0_ARCHITECTURE.md             # Contratos de interfaz MIC
└── config/
    └── config.yaml
```

---

## 7. Resumen de versiones

| | PA v1 (MVP) | PA v2 (r2) |
|---|---|---|
| `main.py` | 587 líneas, StateManager, `time.sleep()` | ~380 líneas, thin pipe |
| StateManager | Activo en `core/` (497 líneas) | Cuarentenado |
| Contratos de interfaz | Ninguno | `pa_outputs.py` + `pa_inputs.py` |
| Kill states | No existían | NORMAL / SOFTKILL / HARDKILL / LOCKOUT |
| Failsafe heartbeat | No existía | 4 etapas de escalada |
| Pacing recovery | Solo log del error | Queue + cooldown exponencial |
| Position.market_value | Stub devolviendo None | Eliminado (responsabilidad del MIC) |
| Tests | 44 (100% passing) | 122 (100% passing) |
| Tiempo de conexión | < 1 segundo | < 1 segundo |
| Latencia de órdenes | < 100ms | < 100ms |

---

## 8. Trabajo paralelo — infraestructura de datos históricos

En paralelo al desarrollo del PA, se construyó una infraestructura completa de descarga y procesamiento de datos históricos para satisfacer el pedido de Pete Davis: barras de 5 segundos para 4 símbolos durante 12 meses (febrero 2025 → enero 2026).

### 8.1 El pipeline

**Paso 1 — Descarga de barras 1s:**

- Para equities (SPY): Databento API, dataset `DBEQ.BASIC`, schema `ohlcv-1s`
- Para futuros CME (ES): Databento API, dataset `GLBX.MDP3`, contrato continuo `ES.v.0`
- Para FX spot (EURUSD, AUDJPY): Massive.com API, símbolos `C:EURUSD` y `C:AUDJPY`

La descarga se hace mes a mes. Cada archivo mensual tiene entre 700,000 y 1,200,000 filas de barras de 1 segundo. Los archivos se guardan en `data/raw_1s/{símbolo}/`.

**Desafío técnico resuelto con Massive.com:** El método `list_aggs()` de la API de Massive cuelga indefinidamente cuando se usa con símbolos FX (C:EURUSD, C:AUDJPY). Después de debugging, se determinó que el problema es interno de su API para el mercado FX. La solución fue usar `get_aggs()` en lugar de `list_aggs()`, iterando día a día (un request por día calendario), acumulando los resultados en un DataFrame mensual.

**Paso 2 — Resampling:**

Las barras de 1s se agregan a múltiples timeframes usando pandas `resample()` con reglas OHLCV estándar:
- Open: primer valor del periodo
- High: máximo del periodo
- Low: mínimo del periodo
- Close: último valor del periodo
- Volume: suma del periodo

Timeframes disponibles: 5s, 15s, 30s, 1min, 3min, 5min. Los archivos resampled se guardan en `data/aggregated/{timeframe}/{símbolo}/`.

**Paso 3 — Entrega:**

Los archivos 5s finales se copian a `delivery/pete_5s_Feb2025_Jan2026/{símbolo}/` listos para subir a Google Drive.

### 8.2 Entregables completados para Pete

| Símbolo | Fuente | Tipo | Archivos | Periodo |
|---|---|---|---|---|
| SPY | Databento DBEQ.BASIC | Equity ETF | 12 | Feb 2025 – Ene 2026 |
| ES (ES.v.0) | Databento GLBX.MDP3 | Futuro CME | 12 | Feb 2025 – Ene 2026 |
| EURUSD | Massive.com C:EURUSD | FX spot | 12 | Feb 2025 – Ene 2026 |
| AUDJPY | Massive.com C:AUDJPY | FX spot | 12 | Feb 2025 – Ene 2026 |

**Total: 48 archivos CSV de barras 5s**, ~250,000–310,000 filas por archivo.

---

## 9. Estado actual del proyecto

| Componente | Estado | Notas |
|---|---|---|
| PA v1 MVP | ✅ Completo | Comiteado como `0413c23` |
| PA v2 (r2) — interfaz formal | ✅ Completo | `pa_outputs.py` + `pa_inputs.py` |
| PA v2 (r2) — kill states | ✅ Completo | 4 estados, transiciones validadas |
| PA v2 (r2) — failsafe heartbeat | ✅ Completo | 4 etapas de escalada |
| PA v2 (r2) — pacing recovery | ✅ Completo | Queue + cooldown exponencial |
| PA v2 (r2) — tests (122) | ✅ Completo | 100% passing |
| Datos históricos Pete (48 archivos) | ✅ Completo | Listo para Google Drive |
| Integración PA ↔ MIC ↔ OE | 🔜 Próximo paso | Contratos de interfaz listos |

---

## 10. ¿Qué sigue?

El PA está diseñado y construido para ser el componente de infraestructura que no hay que volver a tocar. Los contratos de interfaz (`pa_outputs.py` y `pa_inputs.py`) son el punto de integración — cualquier componente nuevo que quiera hablar con el PA solo necesita conocer esos dos archivos.

El siguiente paso natural es construir el **MIC (Market Intelligence Center)**: el módulo que consume los eventos del PA, mantiene el estado del portafolio, calcula métricas de riesgo, y toma decisiones sobre cuándo y cómo ejecutar estrategias. El MIC ya tiene los contratos definidos desde el lado del PA — sabe exactamente qué datos va a recibir y en qué formato.

Después del MIC viene el **OE (Order Execution layer)**: la lógica de estrategia que decide qué órdenes mandar y cuándo. El OE habla con el PA a través de `pa_inputs.py` y escucha sus resultados a través de `pa_outputs.py`. Los contratos ya están.

En otras palabras: el trabajo más difícil de la plataforma — la integración con el broker, la estabilidad de conexión, la seguridad ante fallos — ya está resuelto y probado. Lo que sigue es construir sobre esa base.

