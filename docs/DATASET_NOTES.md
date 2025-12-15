# 📝 NOTAS IMPORTANTES - Datasets de Databento

## ✅ Pipeline Probado y Funcionando

El pipeline ha sido completamente probado con:
- **Symbol:** SPY
- **Dataset:** DBEQ.BASIC
- **Período:** Enero 2024
- **Resultado:** ✅ Éxito total (277,507 barras descargadas, agregadas y validadas)

---

## 🎯 Datasets Disponibles

### Para US Equities (SPY, AAPL, MSFT, etc.)
```bash
--dataset DBEQ.BASIC    # ✅ Recomendado - Funciona perfectamente
--dataset XNAS.ITCH     # ✅ Disponible - NASDAQ
```

### Para CME Futures (ES, NQ, YM, etc.)
```bash
--dataset GLBX.MDP3     # ✅ Disponible - Requiere contrato específico
```

**⚠️ IMPORTANTE para Futures:**
- NO usar "ES" → Usar "ESH24" (contrato específico)
- NO usar "NQ" → Usar "NQM24" (contrato específico)
- Formato: [SÍMBOLO][MES][AÑO]
  - H = Marzo, M = Junio, U = Septiembre, Z = Diciembre

### Para US Options
```bash
--dataset OPRA.PILLAR   # ✅ Disponible
```

---

## 📋 Ejemplos Probados

### ✅ FUNCIONA - SPY con DBEQ.BASIC
```bash
python scripts/fetch_1s_bars.py \
  --symbol SPY \
  --dataset DBEQ.BASIC \
  --start 2024-01-01 \
  --end 2024-01-31

# Resultado: ✅ 277,507 barras descargadas
```

### ❌ NO FUNCIONA - ES sin contrato específico
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --dataset GLBX.MDP3 \
  --start 2024-01-01 \
  --end 2024-01-31

# Error: Symbol did not resolve
```

### ✅ DEBERÍA FUNCIONAR - ES con contrato específico
```bash
python scripts/fetch_1s_bars.py \
  --symbol ESH24 \
  --dataset GLBX.MDP3 \
  --start 2024-01-01 \
  --end 2024-03-15

# ESH24 = E-mini S&P 500, Marzo 2024
```

---

## 🔍 Cómo Explorar Datasets

Usa el script incluido:
```bash
python explore_datasets.py
```

Esto muestra:
- Todos los datasets disponibles (27 en tu cuenta)
- Schemas soportados por cada dataset
- Recomendaciones específicas

---

## 💡 Workflow Recomendado

### Para Trading de Equities
```bash
# 1. Descargar múltiples símbolos
for symbol in SPY QQQ AAPL MSFT; do
  python scripts/fetch_1s_bars.py \
    --symbol $symbol \
    --dataset DBEQ.BASIC \
    --start 2024-01-01 \
    --end 2024-12-31
done

# 2. Agregar todos
for symbol in SPY QQQ AAPL MSFT; do
  python scripts/resample_bars.py --symbol $symbol
done

# 3. Validar
python scripts/validate_bars.py --input_dir data/aggregated/15s --timeframe 15s
```

### Para Trading de Futures
```bash
# Descargar contrato específico de ES
python scripts/fetch_1s_bars.py \
  --symbol ESH24 \
  --dataset GLBX.MDP3 \
  --start 2024-01-01 \
  --end 2024-03-15

# Agregar
python scripts/resample_bars.py --symbol ESH24

# Validar
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

---

## 🚨 Errores Comunes y Soluciones

### Error: "Symbol did not resolve"
**Problema:** Dataset incorrecto para el símbolo

**Solución:**
1. Para equities: usar `--dataset DBEQ.BASIC`
2. Para futures: usar contrato específico (ESH24, no ES)
3. Explorar datasets: `python explore_datasets.py`

### Error: "No data found"
**Problema:** Fecha fuera de rango o mercado cerrado

**Solución:**
1. Verificar que el símbolo existe en esa fecha
2. Evitar fines de semana/festivos
3. Para futures, verificar fecha de expiración del contrato

---

## 📊 Schemas Disponibles

Todos estos datasets soportan `ohlcv-1s`:
- ✅ DBEQ.BASIC
- ✅ GLBX.MDP3
- ✅ XNAS.ITCH
- ✅ Todos los exchanges principales

---

## 🎯 Próximos Pasos

1. **Probar con más símbolos:** AAPL, MSFT, TSLA, etc.
2. **Probar con futures:** ESH24, NQM24
3. **Extender fechas:** Todo 2024 o múltiples años
4. **Empaquetar para entrega** cuando estés satisfecho

---

**Última actualización:** 15 diciembre 2025  
**Estado:** ✅ Pipeline completamente operativo con SPY
