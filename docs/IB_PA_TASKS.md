# Platform Adapter - Interactive Brokers API
**Fecha de inicio:** 21 de enero de 2026  
**Cliente:** Pete Davis / RaptorTrade  
**Proyecto:** PA MVP - Interactive Brokers Integration

---

## 📋 Contexto del Proyecto

### Alcance Limitado (MVP)
- **INCLUIR:** Conexión con Interactive Brokers API únicamente
- **NO INCLUIR:** Conexiones con otros módulos (U, OE) - viene en fase posterior
- **Objetivo:** Platform Adapter funcional conectado a IB

### Credenciales Proporcionadas
```
Usuario: raptortrade
Password: 8UX7RGqmVRQ@sUVVBgjt
Site: interactivebrokers.com
```

### Recursos de Documentación
- **API Options:** https://www.interactivebrokers.com/en/trading/ib-api.php
- **TWS API Docs:** https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- **API Reference:** https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/

---

## 🎯 FASE 1: Investigación y Estimación (⏱️ Máximo 2 horas)

### ✅ Entregables Requeridos

1. **Especificación Rápida**
   - Documento breve explicando arquitectura del PA
   - Decisión de cuál API usar (probablemente TWS API)
   - Estimación de horas totales del proyecto

2. **Task List con Estimaciones**
   - Lista de tareas necesarias
   - No muy detallada, suficiente para entender scope
   - Estimación de horas por tarea
   - Total de horas del proyecto

---

## 📝 TAREAS - FASE 1: Research & Planning

### Tarea 1: Investigar Opciones de API IB
**Tiempo estimado:** 30-45 minutos

**Acciones:**
- [ ] Fetch documentación de https://www.interactivebrokers.com/en/trading/ib-api.php
- [ ] Analizar opciones disponibles (TWS API, Web API, Mobile API, etc.)
- [ ] Identificar requisitos de cada opción
- [ ] Determinar cuál API usar (confirmar TWS API)
- [ ] Documentar decisión con justificación

**Criterios de Decisión:**
- Full feature access ✅
- Market data streaming capability
- Order execution capability
- Python support
- Authentication requirements

---

### Tarea 2: Analizar Documentación TWS API
**Tiempo estimado:** 30-45 minutos

**Acciones:**
- [ ] Fetch documentación de https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- [ ] Identificar proceso de autenticación
- [ ] Identificar endpoints clave:
  - Market data subscription
  - Order placement/management
  - Account information
  - Position tracking
- [ ] Identificar bibliotecas Python disponibles (ibapi, ib_insync, etc.)
- [ ] Identificar requisitos previos (TWS/IB Gateway installation?)

---

### Tarea 3: Crear Especificación Rápida del PA
**Tiempo estimado:** 30-45 minutos

**Entregable:** Documento MD con:
- [ ] Arquitectura propuesta del Platform Adapter
- [ ] Componentes principales
- [ ] Flujo de datos
- [ ] Tecnologías a usar (Python, bibliotecas, etc.)
- [ ] Requisitos de setup
- [ ] Justificación de decisiones técnicas
- [ ] Estimación total de horas del proyecto

**Secciones del Doc:**
1. Resumen ejecutivo
2. Decisión de API (cuál y por qué)
3. Arquitectura del PA
4. Componentes principales
5. Tecnologías y bibliotecas
6. Requisitos y dependencias
7. Estimación total de horas

---

### Tarea 4: Crear Task List Detallada con Estimaciones
**Tiempo estimado:** 15-30 minutos

**Entregable:** Task list completa con:
- [ ] Todas las fases del proyecto
- [ ] Tareas por fase (nivel medio de detalle)
- [ ] Estimación de horas por tarea
- [ ] Dependencias entre tareas
- [ ] Total de horas del proyecto

**Fases Esperadas:**
1. Setup & Configuration
2. Authentication & Connection
3. Market Data Integration
4. Order Execution
5. Testing
6. Documentation
7. Delivery

---

## ⏱️ Estimación Fase 1
- **Tarea 1:** 30-45 min
- **Tarea 2:** 30-45 min
- **Tarea 3:** 30-45 min
- **Tarea 4:** 15-30 min
- **TOTAL:** ~2 horas máximo

---

## 📊 FASE 2: Implementación (Después de aprobación)

### Pendiente de definir después de completar Fase 1

Las tareas específicas dependerán de:
- Decisión final sobre API a usar
- Arquitectura aprobada
- Complejidad identificada en la investigación

**Estimación preliminar:** 1-3 días de desarrollo (a confirmar en Fase 1)

---

## 🚨 Notas Importantes

### Cambio de Proyecto
- **ANTERIOR:** Tradovate API (bloqueado por falta de API key)
- **ACTUAL:** Interactive Brokers API (nuevo proyecto)

### Limitaciones de MVP
- **NO implementar:** Conexión con módulo U (data provider)
- **NO implementar:** Conexión con módulo OE (order engine)
- **SOLO:** Conexión directa con IB API
- Integraciones con otros módulos vendrán en fase posterior

### Límite de Tiempo Fase 1
- Pete Davis especificó: **máximo 2 horas** para investigación
- Si toma más, notificar para tracking de horas

---

## 📞 Contacto
**Cliente:** Pete Davis  
**Proyecto:** Platform Adapter MVP  
**Deadline Fase 1:** ASAP (máximo 2 horas de trabajo)

---

## ✅ Checklist de Entrega Fase 1

Antes de reportar completado, verificar que existe:

- [ ] Documento de especificación rápida (spec)
- [ ] Decisión documentada de cuál API usar
- [ ] Justificación de la decisión
- [ ] Arquitectura propuesta del PA
- [ ] Task list completa con estimaciones
- [ ] Total de horas estimadas para el proyecto
- [ ] Todo en formato claro y conciso

---

**Estado:** 🟡 Por iniciar  
**Próxima acción:** Comenzar Tarea 1 - Investigar opciones de API IB
