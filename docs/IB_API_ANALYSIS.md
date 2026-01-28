# Análisis de Opciones de API de Interactive Brokers
**Fecha de análisis:** Enero 21, 2026  
**Objetivo:** Determinar la mejor opción de API para trading algorítmico

---

## 1. RESUMEN EJECUTIVO

Interactive Brokers ofrece tres opciones principales de API:

1. **TWS API (Trader Workstation API)** - TCP Socket Protocol
2. **Web API (Client Portal API)** - RESTful API con OAuth 2.0
3. **FIX API** - Para instituciones (fuera de alcance para este análisis)

### ✅ Recomendación: TWS API es la opción óptima para tu caso de uso.

---

## 2. OPCIONES DISPONIBLES

### 2.1 TWS API (Trader Workstation API)

**Descripción:**
- API basada en protocolo TCP Socket
- Requiere TWS o IB Gateway corriendo localmente
- Versión actual: 9.72+ (requiere TWS build 952.x o superior)

**Características Principales:**

✅ **Full feature access** - Acceso completo a todas las funcionalidades de trading  
✅ **Market data streaming** - Maneja cientos o miles de líneas de market data simultáneamente  
✅ **Order execution** - Colocación de órdenes avanzadas y algos  
✅ **Python support** - Soporte oficial con versión mínima Python 3.11.0  
✅ **Historical data** - Acceso a datos históricos con diferentes timeframes  
✅ **Real-time bars** - Barras en tiempo real cada 5 segundos  
✅ **Tick-by-tick data** - Datos tick por tick disponibles  
✅ **Account management** - Gestión completa de cuenta y portfolio

**Lenguajes Soportados:**
- Python (3.11.0+)
- Java (Java 21+)
- C++ (C++14 Standard)
- C# (Windows exclusivo)
- VB (Windows exclusivo)

**Requisitos de Autenticación:**
- TWS o IB Gateway instalado
- Login manual con usuario y contraseña (GUI requerido)
- No soporta operación "headless" por razones de seguridad
- Auto-restart disponible desde versión 974+
- Puerto por defecto: 7496 (producción), 7497 (paper trading)
- IB Gateway usa: 4001 (producción), 4002 (paper trading)

**Market Data:**
- Requiere suscripciones de market data para instrumentos específicos
- Requiere cuenta fondeada (excepto forex y bonds)
- Permisos de trading para instrumentos específicos
- Market data compartido entre paper y live (configuración en Account Management)
- Límite de líneas de market data simultáneas depende del plan

**Ventajas:**
- ✅ API más madura y estable (años en producción)
- ✅ Documentación extensa con ejemplos en múltiples lenguajes
- ✅ Asíncrona - diseñada para alta carga de datos
- ✅ Sin límites en mensajes recibidos del servidor
- ✅ Maneja grandes volúmenes de datos y órdenes
- ✅ Librería `ib_insync` disponible (wrapper Python simplificado)
- ✅ Testbed samples disponibles para cada lenguaje
- ✅ Comunidad grande y activa

**Desventajas:**
- ❌ Requiere TWS o IB Gateway corriendo (consume ~40% menos recursos con Gateway)
- ❌ Login manual requerido (no auto-login por seguridad)
- ❌ Requiere restart diario (auto-restart disponible desde v974+)
- ❌ Curva de aprendizaje más pronunciada
- ❌ Arquitectura legacy (pero funcional y probada)

**Rate Limits:**
- Cliente puede enviar hasta 50 mensajes por segundo
- Sin límites en mensajes recibidos del servidor

---

### 2.2 Web API (Client Portal API)

**Descripción:**
- RESTful API moderna con OAuth 2.0
- Comunicación vía HTTP/HTTPS y WebSockets
- Requiere Client Portal Gateway (programa Java) para autenticación individual

**Características Principales:**

✅ **REST architecture** - Estándar web moderno  
✅ **Python support** - Compatible con cualquier lenguaje que soporte HTTP  
⚠️ **Market data streaming** - Disponible vía WebSockets pero menos robusto que TWS  
⚠️ **Order execution** - Disponible pero con limitaciones  
⚠️ **Feature parity** - No tiene completa paridad con TWS API aún

**Requisitos de Autenticación:**

*Para Clientes Individuales:*
- Client Portal Gateway (programa Java)
- Login manual con username y password
- 2FA obligatorio
- Refresh diario de sesión requerido
- Java Runtime Environment (JRE) versión 8 update 192 o superior

*Para Instituciones:*
- OAuth 1.0a o OAuth 2.0
- Proceso de onboarding requerido

**Ventajas:**
- ✅ Lightweight - menos recursos que TWS/Gateway
- ✅ Arquitectura REST moderna
- ✅ WebSocket streaming disponible
- ✅ No requiere TWS UI (solo Gateway para individuales)
- ✅ JSON responses - fácil de parsear
- ✅ Compatible con cualquier lenguaje de programación

**Desventajas:**
- ⚠️ **Limitación crítica:** "No está dirigida a usuarios que buscan automatizar operaciones a gran escala. Para alta carga de requests (ej. docenas de órdenes simultáneas o grandes cantidades de market data), se recomienda TWS API"
- ❌ API más nueva - menos madura que TWS API
- ❌ No tiene completa paridad de features con TWS API
- ❌ 2FA obligatorio para cada login
- ❌ No auto-login disponible
- ❌ Sesión única por username (conflicto con otras plataformas IB)
- ❌ Documentación menos extensa que TWS API

**Rate Limits:**
- Client Portal Gateway: 10 requests/segundo (más restrictivo)
- OAuth: 50 requests/segundo
- Penalty box de 10-15 minutos si se exceden límites
- Límites específicos por endpoint

---

### 2.3 FIX API

**Descripción:**
- Para instituciones y brokers
- Requiere VPN, extranet, leased line o Cross-connect
- Fuera del alcance de este análisis (orientado a instituciones)

---

## 3. COMPARACIÓN DIRECTA

| Característica | TWS API | Web API (Client Portal) |
|----------------|---------|-------------------------|
| **Tipo** | TCP Socket | REST + WebSocket |
| **Madurez** | +++++ (años en producción) | +++ (más reciente) |
| **Market Data Streaming** | +++++ (diseñado para esto) | +++ (disponible pero limitado) |
| **Order Execution** | +++++ (full featured) | +++ (básico) |
| **Python Support** | ✅ Oficial | ✅ Compatible |
| **Auto-login** | ❌ (seguridad) | ❌ (2FA obligatorio) |
| **Rate Limits** | 50 msg/sec (cliente) | 10 req/sec (Gateway) |
| **Recursos Sistema** | Alto (TWS) / Medio (Gateway) | Bajo (solo Gateway) |
| **Setup Complexity** | Media-Alta | Media |
| **Feature Completeness** | 100% | ~80% (en desarrollo) |
| **High Frequency Trading** | ✅ Recomendado | ❌ No recomendado |
| **Large Data Sets** | ✅ Diseñado para esto | ⚠️ Limitaciones |
| **Documentation** | +++++ Extensa | +++ Buena pero menor |
| **Community Support** | +++++ Grande | ++ Creciendo |

---

## 4. CONSIDERACIONES DE MARKET DATA

### Requisitos Generales (aplican a ambas APIs):
- Cuenta fondeada (excepto forex y bonds)
- Trading permissions para instrumentos específicos
- Market data subscriptions activas para los instrumentos
- Configuración en Account Management

### Market Data con TWS API:
- Streaming optimizado para miles de líneas simultáneas
- `reqMktData()` para watchlist data (snapshots agregados varias veces por segundo)
- `reqTickByTickData()` para tick-by-tick data
- `reqHistoricalData()` para datos históricos con streaming opcional
- `reqRealTimeBars()` para barras de 5 segundos en tiempo real
- Market data lines limitadas según plan (ejemplo: 100 base + booster packs de 100 líneas por $30/mes)

### Market Data con Web API:
- WebSocket streaming disponible
- Menor throughput que TWS API
- Recomendado para casos de uso más ligeros

---

## 5. SETUP Y AUTENTICACIÓN

### TWS API Setup:

**Paso 1: Instalar TWS o IB Gateway**
- Descargar de https://www.interactivebrokers.com/en/trading/ib-api.php
- TWS: Full featured con GUI
- IB Gateway: Sin GUI, consume 40% menos recursos (recomendado para API)

**Paso 2: Instalar TWS API**
- Descargar API Components
- Python: versión 3.11.0 o superior
- Instalar librería: `pip install ibapi`
- (Opcional) Instalar `ib_insync` para wrapper simplificado: `pip install ib_insync`

**Paso 3: Configurar TWS/Gateway**
- Edit → Global Configuration → API → Settings
- Enable "ActiveX and Socket Clients"
- Socket Port: 7496 (live) / 7497 (paper)
- Trusted IP: 127.0.0.1 (localhost)

**Paso 4: Auto-restart (Opcional, v974+)**
- Configurar restart diario automático
- Permite correr Lunes-Sábado sin re-autenticación
- Domingo requiere re-login después de server reset

**Paso 5: Conectar desde Python**
```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

app = IBApp()
app.connect("127.0.0.1", 7497, clientId=1)  # 7497 for paper trading
```

---

### Web API Setup:

**Paso 1: Instalar Java**
- JRE 8 update 192 o superior
- Verificar: `java -version`

**Paso 2: Descargar Client Portal Gateway**
- Desde https://interactivebrokers.github.io/cpwebapi/

**Paso 3: Ejecutar Gateway**
```bash
java -jar clientportal.gw.jar
```

**Paso 4: Autenticar**
- Abrir navegador: https://localhost:5000/
- Login con usuario/contraseña IB
- 2FA requerido
- Sesión válida ~24 horas

**Paso 5: Hacer Requests desde Python**
```python
import requests

base_url = "https://localhost:5000/v1/api"
response = requests.get(f"{base_url}/portfolio/accounts")
```

---

## 6. LIBRERÍAS PYTHON DISPONIBLES

### Para TWS API:

**ibapi (oficial)**
- Librería oficial de Interactive Brokers
- Más bajo nivel, más control
- Requiere manejo manual de threads

**ib_insync (third-party)**
- Wrapper sobre ibapi
- API más Pythonic
- Manejo automático de threads
- Más fácil de usar
- Documentación: https://ib-insync.readthedocs.io/

### Para Web API:

**requests + websockets**
- Librerías estándar Python
- Construir tu propia implementación

**interactive-broker-python-api (third-party)**
- Wrapper sobre Web API
- Maneja autenticación y sesiones
- https://github.com/areed1192/interactive-broker-python-api

---

## 7. DECISIÓN Y JUSTIFICACIÓN

### ✅ RECOMENDACIÓN: TWS API

**Justificación:**

1. **Full Feature Access ✅**
   - TWS API ofrece acceso completo a todas las funcionalidades
   - Web API todavía no tiene paridad completa

2. **Market Data Streaming ✅**
   - TWS API está diseñado específicamente para manejar grandes volúmenes de datos
   - Asíncrono, optimizado para cientos/miles de líneas simultáneas
   - Web API tiene limitaciones para uso intensivo de datos

3. **Order Execution ✅**
   - TWS API soporta todos los tipos de órdenes avanzadas y algos
   - Capacidad probada para alta frecuencia

4. **Python Support ✅**
   - Soporte oficial completo
   - Múltiples librerías disponibles (ibapi, ib_insync)
   - Documentación extensa con ejemplos

5. **Stability & Maturity ✅**
   - API madura con años de uso en producción
   - Comunidad grande y activa
   - Casos de uso extensamente documentados

6. **Performance ✅**
   - Diseñado para trading algorítmico intensivo
   - Sin límites en mensajes recibidos
   - 50 mensajes/segundo desde cliente (suficiente para mayoría de casos)

**Trade-offs Aceptables:**
- ❌ Requiere TWS/Gateway corriendo (pero IB Gateway usa recursos mínimos)
- ❌ Login manual (pero auto-restart permite correr 6 días sin intervención)
- ❌ Curva de aprendizaje (pero compensada por documentación y librerías)

**Por qué NO Web API:**

La documentación oficial de IB es clara:

> "The Client Portal API is primarily targeted towards developers looking to create custom user interfaces with some trading and market data capabilities. It is not aimed at users looking to automate, at scale, common operations done through other platforms. For users looking to develop solutions that require a high throughput of requests, for example placing dozens of orders at a time, or subscribing to large amounts of market data, we recommend the TWS API instead."

---

## 8. PLAN DE IMPLEMENTACIÓN

### Fase 1: Setup Inicial (1-2 días)
- Abrir cuenta IB y obtener aprobaciones
- Configurar Paper Trading Account
- Instalar IB Gateway
- Instalar Python y librerías necesarias
- Verificar market data subscriptions

### Fase 2: Desarrollo Base (3-5 días)
- Implementar conexión con IB Gateway
- Implementar market data streaming
- Implementar order placement básico
- Testing con Paper Trading Account

### Fase 3: Features Avanzadas (1-2 semanas)
- Implementar estrategia de trading
- Manejo de errores y reconexión
- Logging y monitoring
- Backtesting con historical data

### Fase 4: Production (1 semana)
- Testing extensivo en Paper Trading
- Optimización de performance
- Setup de auto-restart
- Deploy a producción con cuenta real

---

## 9. RECURSOS Y DOCUMENTACIÓN

### Documentación Oficial:
- **TWS API Home:** https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- **TWS API Reference:** https://interactivebrokers.github.io/tws-api/
- **Client Portal API:** https://interactivebrokers.github.io/cpwebapi/
- **IBKR Campus:** https://www.interactivebrokers.com/campus/ibkr-api-page/

### Tutoriales y Cursos:
- **Python TWS API Course:** https://www.interactivebrokers.com/campus/trading-course/python-tws-api/
- **TWS API Tutorial Series:** Videos y tutoriales paso a paso
- **GitHub Repository:** https://github.com/InteractiveBrokers/tws-api-public

### Librerías Python:
- **ibapi (oficial):** Viene con instalación de TWS API
- **ib_insync:** `pip install ib_insync` - https://ib-insync.readthedocs.io/
- **Interactive Brokers Forum:** https://groups.io/g/twsapi

### Comunidad:
- **IB API Forum:** https://groups.io/g/twsapi
- **Reddit:** r/algotrading
- **Stack Overflow:** Tag [interactive-brokers]

---

## 10. CONSIDERACIONES ADICIONALES

### Market Data Costs:
- Verificar costos de market data subscriptions
- Base: ~$10-30/mes por exchange/producto
- Market data lines adicionales disponibles por ~$30/mes (100 líneas)

### Account Requirements:
- Cuenta fondeada (mínimos varían por tipo de cuenta)
- Trading permissions configuradas
- Paper Trading gratis para testing

### Maintenance:
- Restart diario (automatizable desde v974+)
- Monitoreo de conexión y reconexión automática
- Mantenimiento semanal (Domingo después de server reset)

### Backup Plan:
- Si TWS API no funciona como esperado, Web API es opción secundaria
- FIX API para necesidades institucionales futuras
- Third-party platforms (NinjaTrader, MultiCharts) como alternativa

---

## 11. CONCLUSIÓN

**TWS API es la opción recomendada por:**

✅ Full feature access - Acceso completo a todas las funcionalidades  
✅ Market data streaming capability - Diseñado para grandes volúmenes  
✅ Order execution capability - Órdenes avanzadas y alta frecuencia  
✅ Python support - Soporte oficial completo con librerías maduras  
✅ Proven stability - Años de uso en producción

Los requisitos de autenticación (login manual, Gateway running) son trade-offs aceptables considerando las ventajas significativas en features, performance y estabilidad.

### Próximos Pasos:

- ✅ Investigación de opciones de API - **COMPLETADO**
- 🔄 Setup de IB Gateway y Paper Trading Account
- 🔄 Implementación de conexión básica con TWS API
- 🔄 Testing de market data streaming
- 🔄 Desarrollo de estrategia de trading

---

## Referencias

- Todas las URLs citadas verificadas el 21 de Enero, 2026
- Información obtenida de documentación oficial de Interactive Brokers
- Comparaciones basadas en especificaciones técnicas oficiales

---

**Fecha de análisis:** Enero 21, 2026  
**Status:** ✅ Tarea 1 Completada  
**Tiempo invertido:** ~45 minutos
