# 📋 PA MVP - Checklist Simplificado

**Timeline:** 2-3 días | **Entrega:** 14-15 enero 2026

---

## ✅ FASE 1: PREPARACIÓN (0.5 día) - COMPLETADA

- [x] Responder a Pete/JK
- [x] Hacer preguntas críticas (repo, stack, transport, ambiente)
- [x] Ver video Loom
- [x] Leer MVP spec completo
- [x] Estudiar TDV docs (placeOrder, bar stream)

---

## 🔍 FASE 2: DISCOVERY (0.5-1 día)

### Setup
- [ ] Recibir credenciales Tradovate demo
- [ ] Crear script test de conexión
- [ ] Probar autenticación con API

### Market Data Research
- [ ] Probar ticks vs bars
- [ ] Probar intervalos (1s, 15s, 30s, 1m)
- [ ] Verificar orden de entrega
- [ ] Verificar duplicados en reconnect
- [ ] Documentar comportamiento de replay

### Seq IDs Research
- [ ] Verificar si existe seq en bars
- [ ] Verificar scope (per symbol/session/global)
- [ ] Verificar reset behavior
- [ ] Verificar seq en execution events
- [ ] Documentar identificadores (account, order, fill IDs)

### Reliability Research
- [ ] Identificar rate limits
- [ ] Probar reconnect behavior
- [ ] Verificar heartbeat/keepalive requirements

### Deliverable
- [ ] Crear `DISCOVERY_REPORT.md` con findings

---

## 🏗️ FASE 3: DISEÑO (0.25 día = 2-3 horas)

- [ ] Definir estructura de carpetas
- [ ] Definir interfaces (ITradovateConnector, IMarketDataAdapter, IExecutionAdapter, IForwarder)
- [ ] Diseñar config schema (YAML/JSON)
- [ ] Diseñar secrets handling (.env)
- [ ] Proponer transport PA↔U y OE↔PA
- [ ] Escalar propuesta a Pete/JK

---

## 💻 FASE 4: IMPLEMENTACIÓN (0.5-1 día)

### Setup
- [ ] Clonar/crear repo
- [ ] Setup venv
- [ ] Crear requirements.txt
- [ ] Configurar .gitignore
- [ ] Setup linting (ruff/black)

### Core Implementation
- [ ] Implementar Tradovate connector (auth, connection, reconnect, heartbeat)
- [ ] Implementar Market Data Adapter (WebSocket, parsing, timestamp preservation, seq mapping, forward to U)
- [ ] Implementar Execution Adapter (receive intents, translate to TDV calls, return receipt-ack, error handling)
- [ ] Implementar Event Listener (listen fills/rejects/account, forward to U, preserve metadata)
- [ ] Implementar Backpressure Handling (detect backpressure, shed telemetry, escalate PA_DEGRADED/PA_DOWN)

---

## 🧪 FASE 5: TESTING (0.25-0.5 día = 2-4 horas)

### Unit Tests
- [ ] Test autenticación
- [ ] Test parsing market data
- [ ] Test order translation
- [ ] Test error handling
- [ ] Test reconnect logic
- [ ] Verificar coverage > 80%

### Integration Tests
- [ ] Test conexión Tradovate demo
- [ ] Test market data subscription
- [ ] Test order placement
- [ ] Test event forwarding
- [ ] Mock módulo U

### Acceptance Tests
- [ ] A) Connectivity (connect, detect disconnects, reconnect, report PA_DEGRADED/DOWN)
- [ ] B) Market Data (subscribe, forward bars, timestamp handling)
- [ ] C) Seq Compliance (forward platform seq, document behavior)
- [ ] D) Execution Path (receive intents, execute, return receipt-ack, emit facts to U)
- [ ] E) Failure Behavior (shed telemetry, escalate, never drop events)

### Chaos Tests
- [ ] Simular network failures
- [ ] Simular TDV API down
- [ ] Simular slow consumer (U)
- [ ] Simular rate limiting
- [ ] Verificar NO pérdida de datos

---

## 📚 FASE 6: DOCUMENTACIÓN (0.25 día = 2 horas)

- [ ] Docstrings en módulos
- [ ] Type hints completos
- [ ] Inline comments
- [ ] Runbook-lite (cómo correr, troubleshooting, logs)
- [ ] Completar Discovery Report
- [ ] README.md (overview, installation, config, usage, testing)

---

## 🚀 FASE 7: ENTREGA (0.25 día = 2 horas)

### Pre-Delivery
- [ ] Acceptance tests passing
- [ ] Code review ready
- [ ] Docs completa
- [ ] Discovery report final
- [ ] No hardcoded credentials
- [ ] .env.example incluido

### Delivery
- [ ] Create PR(s)
- [ ] Update Jira tasks
- [ ] Demo en vivo
- [ ] Walkthrough de código
- [ ] Handoff runbook

### Post-Delivery
- [ ] Address feedback
- [ ] Fix bugs
- [ ] Iterate si necesario

---

## 🚨 REGLAS CRÍTICAS

### ✅ MUST
1. Reenviar datos raw (no fabricar barras)
2. Preservar timestamps de Tradovate
3. Ejecutar solo intents de OE
4. Escalar a OE si hay backpressure
5. Retornar receipt-ack sincrónico

### ❌ MUST NOT
1. NO fabricar datos
2. NO escribir a BarStream/EventStream
3. NO calcular indicadores
4. NO aceptar intents de otros módulos
5. NO perder eventos silenciosamente

---

## 📊 PROGRESO

**Día 1 (12 enero):**
- [x] Fase 1 COMPLETADA
- [ ] Fase 2 Discovery (4-6 horas)

**Día 2 (13 enero):**
- [ ] Fase 3 Diseño (2-3 horas)
- [ ] Fase 4 Implementación parte 1 (4-5 horas)

**Día 3 (14 enero):**
- [ ] Fase 4 Implementación parte 2 (2-3 horas)
- [ ] Fase 5 Testing (2-3 horas)
- [ ] Fase 6 Documentación (2 horas)
- [ ] Fase 7 Entrega (1 hora)

---

## 📚 REFERENCIAS

**Docs:**
- MVP Spec: `/Users/1di/DataBento/docs/mvp/11.1-MVP - PA 2026-01-08.md`
- Place Order: `/Users/1di/DataBento/docs/mvp/TDV-placeOrder.md`
- Bar Stream: `/Users/1di/DataBento/docs/mvp/TDV-bar data stream.md`
- API Docs: `/Users/1di/DataBento/docs/mvp/Tradovate API.md`

**Links:**
- Loom: https://www.loom.com/share/b684e82fa7c6455eb8bd37b4506efa1b
- API: https://api.tradovate.com
- Community: https://community.tradovate.com/c/api-developers/15

**Endpoints:**
```
Live:  https://live.tradovateapi.com
Demo:  https://demo.tradovateapi.com
MD WS: wss://md.tradovateapi.com/v1/websocket
```

---

**Status:** Fase 1 ✅ | **Siguiente:** Fase 2 Discovery | **Entrega:** 14-15 enero
