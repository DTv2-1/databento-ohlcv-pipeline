# 📋 Platform Adapter MVP - Plan de Tareas

**Proyecto:** Platform Adapter (Tradovate)  
**Fecha inicio:** 12 de enero de 2026  
**Estimación total:** 2-3 días (con GitHub Copilot + Claude)  
**Stakeholders:** Pete Davis (PM), JK (Tech Lead)

---

## 🎯 **FASE 1: PREPARACIÓN Y CLARIFICACIÓN (Hoy - 1-2 horas)**

### 1.1 Responder a Pete/JK
- [x] Confirmar recepción del MVP spec y documentación
- [x] Agradecer por el video overview de Loom
- [x] Mencionar que estás revisando todo el material

### 1.2 Preguntas Críticas para Pete/JK
- [x] **Repo:** ¿Dónde está el repositorio del proyecto? ¿GitHub? ¿Link?
- [x] **Stack:** ¿Qué lenguaje usar? (Python/Node.js/C#)
- [x] **Transport:** ¿Qué usar entre PA↔U y OE↔PA? (WebSocket/gRPC/Queue/HTTP)
- [x] **Ambiente:** ¿Hay staging/dev environment configurado?
- [x] **Dependencies:** ¿Existen módulos U/OE/Paper ya implementados para testing?

### 1.3 Ver Material Completo
- [x] Ver video Loom de Pete (link: https://www.loom.com/share/b684e82fa7c6455eb8bd37b4506efa1b)
- [x] Leer completo `11.1-MVP - PA 2026-01-08.md` (317 líneas)
- [x] Estudiar `TDV-placeOrder.md` (291 líneas)
- [x] Estudiar `TDV-bar data stream.md` (360 líneas)
- [x] Revisar `Tradovate API.md` (1081 líneas)

---

## 🔍 **FASE 2: DISCOVERY RESEARCH (0.5-1 día con Copilot + Claude)**

### 2.1 Configurar Acceso a Tradovate
- [ ] Esperar credenciales de demo account de Pete (~1 día)
- [ ] Registrar cuenta en Tradovate community forums
- [ ] Explorar https://api.tradovate.com interactivamente

### 2.2 Testing de Autenticación
- [ ] Crear script de test básico de conexión
- [ ] Probar `POST /v1/auth/accesstokenrequest` en demo
- [ ] Documentar flow de 2FA (deviceId + cid + sec)
- [ ] Verificar expiración de tokens y refresh mechanism

### 2.3 Discovery: Market Data Capabilities
- [ ] **Tipos de datos disponibles:**
  - ¿Tradovate entrega ticks raw?
  - ¿Tradovate entrega bars agregadas?
  - ¿Qué es "true bar" vs "server-side aggregate"?
  
- [ ] **Intervalos nativos disponibles:**
  - Probar 1s bars (¿existe?)
  - Probar 15s bars (elementSize: 0.25 con MinuteBar)
  - Probar 30s bars (elementSize: 0.5)
  - Probar 1m bars (elementSize: 1)
  - Probar custom intervals
  
- [ ] **Semántica de entrega:**
  - Orden de llegada (FIFO? puede haber out-of-order?)
  - Duplicados (¿pueden llegar duplicados en reconnect?)
  - Replay behavior (¿qué pasa al reconectar?)
  - Snapshot vs streaming (¿hay snapshot inicial?)

### 2.4 Discovery: Sequence IDs
- [ ] **Market data seq IDs:**
  - ¿Existe campo `seq` en bars?
  - Si sí: ¿scope? (per symbol / per session / global)
  - ¿Se resetea? ¿Cuándo? (daily / per session)
  - ¿Es monotónico y contiguo?
  
- [ ] **Execution event seq IDs:**
  - ¿Existe `seq` o `event_id` en fills/orders?
  - Scope y semántica
  
- [ ] **Identificadores clave:**
  - Account ID format
  - Subaccount IDs (si existen)
  - Client order ID vs Broker order ID
  - Fill/execution IDs
  - Position IDs

### 2.5 Discovery: Reliability & Limits
- [ ] **Rate limits:**
  - Requests per second/minute
  - WebSocket message limits
  - Subscription limits (cuántos símbolos simultáneos)
  
- [ ] **Reconnect behavior:**
  - ¿Auto-reconnect disponible?
  - ¿Cómo resumir sin perder datos?
  - ¿Hay replay de mensajes perdidos?
  - Backoff policy recomendado
  
- [ ] **Heartbeat/keepalive:**
  - ¿Requiere ping/pong?
  - Timeout de inactividad
  - Disconnect detection

### 2.6 Documentar Discovery Findings
- [ ] Crear `DISCOVERY_REPORT.md` con:
  - Respuestas a todas las preguntas DISCOVERY REQUIRED
  - Screenshots de API responses
  - Links a docs relevantes
  - Recomendaciones técnicas
  - Blockers identificados

---

## 🏗️ **FASE 3: DISEÑO DE ARQUITECTURA PA (0.25 días = 2-3 horas)**

### 3.1 Diseño de Módulo PA
- [ ] Definir estructura de carpetas:
  ```
  pa/
  ├── src/
  │   ├── connectors/
  │   │   └── tradovate.py
  │   ├── adapters/
  │   │   ├── market_data.py
  │   │   └── execution.py
  │   ├── transport/
  │   │   └── u_forwarder.py
  │   ├── config/
  │   │   └── settings.py
  │   └── main.py
  ├── tests/
  ├── config/
  │   ├── config.yaml
  │   └── .env.example
  └── docs/
  ```

- [ ] Definir interfaces/contratos:
  - `ITradovateConnector`
  - `IMarketDataAdapter`
  - `IExecutionAdapter`
  - `IForwarder` (PA → U)

### 3.2 Diseño de Config & Secrets
- [ ] Schema de configuración (YAML/JSON)
- [ ] Manejo de secrets (.env + environment variables)
- [ ] Multi-environment support (demo/live)
- [ ] Instrument list configuration

### 3.3 Propuesta de Transport
- [ ] Investigar opciones (WebSocket/gRPC/RabbitMQ/Redis)
- [ ] Proponer transport PA↔U
- [ ] Proponer transport OE↔PA
- [ ] Documentar pros/cons de cada opción
- [ ] Escalar a Pete/JK para decisión

---

## 💻 **FASE 4: IMPLEMENTACIÓN CORE (0.5-1 día con Copilot + Claude)**

### 4.1 Setup Inicial
- [ ] Clonar/crear repo
- [ ] Setup Python virtual environment
- [ ] Crear `requirements.txt` / `pyproject.toml`
- [ ] Configurar `.gitignore`
- [ ] Setup pre-commit hooks
- [ ] Configurar linting (ruff/black)

### 4.2 Implementar Tradovate Connector
- [ ] Autenticación con Tradovate
- [ ] Connection management
- [ ] Reconnect logic con exponential backoff
- [ ] Health check / heartbeat
- [ ] Error handling robusto

### 4.3 Implementar Market Data Adapter
- [ ] WebSocket subscription a Tradovate
- [ ] Parsing de bars/ticks
- [ ] Timestamp preservation
- [ ] Seq ID mapping (si disponible)
- [ ] Forwarding a U (sin modificaciones)

### 4.4 Implementar Execution Adapter
- [ ] Recibir intents de OE
- [ ] Traducir a Tradovate API calls
- [ ] Retornar receipt-ack sincrónico
- [ ] Error handling (immediate failures)
- [ ] Correlation ID tracking

### 4.5 Implementar Event Listener
- [ ] Escuchar execution events (fills/rejects)
- [ ] Escuchar account events
- [ ] Forward raw a U (para EventStream)
- [ ] Preservar platform metadata

### 4.6 Implementar Backpressure Handling
- [ ] Detectar backpressure en forwarding a U
- [ ] Shed telemetry first (logs/metrics)
- [ ] Escalar PA_DEGRADED a OE
- [ ] Escalar PA_DOWN a OE
- [ ] NEVER drop canonical events silently

---

## 🧪 **FASE 5: TESTING (0.25-0.5 días = 2-4 horas)**

### 5.1 Unit Tests
- [ ] Test autenticación
- [ ] Test parsing de market data
- [ ] Test order translation
- [ ] Test error handling
- [ ] Test reconnect logic
- [ ] Coverage > 80%

### 5.2 Integration Tests
- [ ] Test conexión a Tradovate demo
- [ ] Test market data subscription
- [ ] Test order placement
- [ ] Test event forwarding
- [ ] Mock de módulo U para testing

### 5.3 Acceptance Tests (del MVP spec)
- [ ] **A) Connectivity:**
  - Conecta/autentica confiablemente
  - Detecta disconnects
  - Reconnect con bounded backoff
  - Reporta PA_DEGRADED/PA_DOWN
  
- [ ] **B) Market Data Forwarding:**
  - Subscribe a instrumentos
  - Forward bars (no fabricadas)
  - Timestamp handling correcto
  
- [ ] **C) Seq Compliance:**
  - Forward platform seq sin cambios (si existe)
  - Leave seq unmapped si no existe
  - Document duplicate/replay behavior
  
- [ ] **D) Execution Path:**
  - Receive intents from OE
  - Execute on Tradovate
  - Return receipt-ack + immediate-failure
  - Emit facts to U (no push to OE)
  
- [ ] **E) Failure Behavior:**
  - Shed telemetry under backpressure
  - Escalate when canonical forwarding at risk
  - Never drop events silently

### 5.4 Chaos Testing
- [ ] Simular network failures
- [ ] Simular Tradovate API down
- [ ] Simular slow consumer (U)
- [ ] Simular rate limiting
- [ ] Verificar NO pérdida de datos

---

## 📚 **FASE 6: DOCUMENTACIÓN (0.25 días = 2 horas)**

### 6.1 Code Documentation
- [ ] Docstrings en todos los módulos
- [ ] Type hints completos
- [ ] Inline comments para lógica compleja

### 6.2 Runbook-Lite
- [ ] Cómo correr localmente
- [ ] Cómo correr en staging
- [ ] Configuración de environment
- [ ] Troubleshooting común
- [ ] Dónde encontrar logs

### 6.3 Discovery Report
- [ ] Completar con findings finales
- [ ] Incluir screenshots/ejemplos
- [ ] Recommendations para arquitectura
- [ ] Open questions/blockers

### 6.4 README.md
- [ ] Overview del módulo
- [ ] Installation instructions
- [ ] Configuration guide
- [ ] Usage examples
- [ ] Testing guide

---

## 🚀 **FASE 7: ENTREGA Y HANDOFF (0.25 días = 2 horas)**

### 7.1 Pre-Delivery Checklist
- [ ] Todos los acceptance tests passing
- [ ] Code review ready
- [ ] Documentación completa
- [ ] Discovery report finalizado
- [ ] No hardcoded credentials
- [ ] .env.example incluido

### 7.2 Entrega a Pete/JK
- [ ] Create PR(s) en repo
- [ ] Update Jira tasks
- [ ] Demo en vivo (si es posible)
- [ ] Walkthrough de código
- [ ] Handoff de runbook

### 7.3 Post-Delivery Support
- [ ] Address feedback/comments
- [ ] Fix bugs identificados
- [ ] Answer questions
- [ ] Iterate si es necesario

---

## ⏱️ **ESTIMACIÓN TOTAL**

| Fase | Original | Con Copilot Solo | **Con Copilot + Claude** |
|------|----------|------------------|--------------------------|
| 1. Preparación | 0.5 | 0.5 | ✅ **0.5** (HECHO) |
| 2. Discovery | 2-3 | 1.5-2 | **0.5-1** ⚡ |
| 3. Diseño | 1 | 0.5 | **0.25** ⚡⚡ |
| 4. Implementación | 3-4 | 1.5-2 | **0.5-1** ⚡⚡⚡ |
| 5. Testing | 2 | 1 | **0.25-0.5** ⚡⚡ |
| 6. Documentación | 1 | 0.5 | **0.25** ⚡⚡ |
| 7. Entrega | 1 | 0.5 | **0.25** ⚡ |

**Total original:** 9-12 días  
**Total con Copilot:** 5-7 días  
**Total con Copilot + Claude:** **2-3 días** (~75% más rápido) 🚀

### 🤖 **Por qué tan rápido con Copilot + Claude:**

**Discovery (0.5-1 día):**
- Claude puede analizar toda la API doc en segundos
- Copilot genera scripts de test automáticamente
- Exploración paralela de múltiples endpoints

**Diseño (0.25 día = 2-3 horas):**
- Claude propone arquitectura completa basada en MVP spec
- Interfaces y contratos generados automáticamente
- Decisiones de transport con pros/cons en minutos

**Implementación (0.5-1 día):**
- Copilot escribe 80% del boilerplate
- Claude revisa y optimiza en tiempo real
- Connector + Adapters + Transport en paralelo
- Error handling y edge cases cubiertos automáticamente

**Testing (0.25-0.5 día):**
- Copilot genera unit tests completos
- Claude diseña acceptance tests
- Mocks y fixtures automáticos
- Coverage > 80% desde el inicio

**Documentación (0.25 día = 2 horas):**
- Docstrings auto-generados por Copilot
- Claude escribe README y runbook
- Discovery report compilado de notas

### 📅 **Timeline Realista:**

**Día 1 (Hoy):**
- ✅ Fase 1 completada
- Fase 2: Discovery research (4-6 horas)

**Día 2:**
- Fase 3: Diseño (2-3 horas)
- Fase 4: Implementación parte 1 (4-5 horas)

**Día 3:**
- Fase 4: Implementación parte 2 (2-3 horas)
- Fase 5: Testing (2-3 horas)
- Fase 6: Documentación (2 horas)
- Fase 7: Entrega (1 hora)

**Buffer:** Medio día extra para iteración/feedback

---

## 🎯 **TAREAS PARA HOY (Enero 12, 2026)**

### Prioridad 1 (Antes de 12 PM)
1. [x] **Responder a Pete/JK** en WhatsApp
   - Confirmar recepción de material
   - Agradecer por docs y video
   - Mencionar que estás iniciando revisión

2. [x] **Hacer preguntas críticas:**
   - ¿Dónde está el repo?
   - ¿Qué stack técnico usar?
   - ¿Qué transport entre módulos?
   - ¿Hay ambiente de staging?
   - ¿Módulos U/OE/Paper existen ya?

3. [x] **Ver video Loom completo**
   - Tomar notas de puntos clave
   - Identificar requirements adicionales

### Prioridad 2 (Tarde)
4. [x] **Leer MVP spec completo**
   - `/Users/1di/DataBento/docs/mvp/11.1-MVP - PA 2026-01-08.md`
   - Anotar MUST/MUST NOT boundaries
   - Anotar DISCOVERY REQUIRED items

5. [x] **Estudiar TDV docs:**
   - `TDV-placeOrder.md` (order placement)
   - `TDV-bar data stream.md` (market data)
   - Identificar gaps de conocimiento

6. [x] **Crear checklist personal**
   - En Notion/Obsidian/papel
   - Priorizar tareas

### Prioridad 3 (Si hay tiempo)
7. [ ] **Explorar Tradovate API docs**
   - https://api.tradovate.com
   - https://community.tradovate.com/c/api-developers/15
   - Buscar ejemplos de código

8. [ ] **Crear proyecto local inicial**
   - Estructura básica de carpetas
   - README.md inicial
   - .gitignore

---

## 📊 **TEMPLATE DE DAILY UPDATE**

Usar este formato para updates a Pete:

```
**[PA MVP] Update - Día X - [Fecha]**

✅ Completado:
- Task 1
- Task 2

🔄 En progreso:
- Task 3 (70% complete)

🚧 Blockers:
- Blocker 1 (descripción)
- Esperando: acceso Tradovate / decisión sobre X

📅 Plan para mañana:
- Task 4
- Task 5

❓ Preguntas:
- Pregunta 1
- Pregunta 2
```

---

## 🚨 **REGLAS CRÍTICAS (Recordatorios)**

### ✅ **MUST (Obligatorio)**
1. Reenviar datos raw sin fabricar barras
2. Preservar timestamps de Tradovate
3. Ejecutar solo intents de OE
4. Escalar a OE si hay backpressure
5. Retornar receipt-ack sincrónico

### ❌ **MUST NOT (Prohibido)**
1. NO fabricar datos
2. NO escribir a BarStream/EventStream
3. NO calcular indicadores
4. NO aceptar intents de otros módulos
5. NO perder eventos silenciosamente

---

## 📚 **REFERENCIAS RÁPIDAS**

### Documentos Clave
- **MVP Spec:** `/Users/1di/DataBento/docs/mvp/11.1-MVP - PA 2026-01-08.md`
- **Place Order:** `/Users/1di/DataBento/docs/mvp/TDV-placeOrder.md`
- **Bar Stream:** `/Users/1di/DataBento/docs/mvp/TDV-bar data stream.md`
- **API Docs:** `/Users/1di/DataBento/docs/mvp/Tradovate API.md`

### Links Importantes
- **Loom Video:** https://www.loom.com/share/b684e82fa7c6455eb8bd37b4506efa1b
- **Tradovate API:** https://api.tradovate.com
- **Support:** https://support.tradovate.com/s/article/Tradovate-API-Access
- **Community:** https://community.tradovate.com/c/api-developers/15

### Endpoints Tradovate
```
Live:  https://live.tradovateapi.com
Demo:  https://demo.tradovateapi.com
MD WS: wss://md.tradovateapi.com/v1/websocket
```

---

## 🎯 **ARQUITECTURA DEL SISTEMA**

```
┌─────────────┐
│ Tradovate   │ (Broker + Market Data)
│   API       │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│     PA      │ ← TU TRABAJO (Platform Adapter)
│ (Tradovate) │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│      U      │ (Unified Ingestion)
│             │ - Escribe BarStream
└──────┬──────┘ - Escribe EventStream
       │
       ↓
┌─────────────┐
│    Paper    │ (Simulation Engine)
│             │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│     OE      │ (Order Execution)
│             │ ← Envia intents a PA
└──────┬──────┘
       │
       ↓
┌─────────────┐
│    Sig      │ (Signal Generator)
│             │
└─────────────┘
```

### Flujos Clave
1. **Market Data:** Tradovate → PA → U → Paper → OE → Sig
2. **Orders:** OE → PA → Tradovate
3. **Events:** Tradovate → PA → U → Paper → OE

---

## 📝 **NOTAS Y DECISIONES**

### Decisiones Pendientes
- [ ] Stack tecnológico (Python/Node/C#)
- [ ] Transport PA↔U (WS/gRPC/Queue)
- [ ] Transport OE↔PA (WS/gRPC/HTTP)
- [ ] Repo location

### Blockers Identificados
- [ ] Esperando credenciales Tradovate demo
- [ ] Esperando acceso a Jira
- [ ] Esperando respuesta sobre repo/stack

### Ideas/Observaciones
- (Agregar aquí conforme surjan)

---

**Última actualización:** 12 de enero de 2026  
**Status:** Fase 1 - COMPLETADA ✅  
**Próximo milestone:** Fase 2 - Discovery (esperando acceso Tradovate)  
**Timeline:** 2-3 días totales con Copilot + Claude 🚀  
**Entrega estimada:** 14-15 de enero de 2026
