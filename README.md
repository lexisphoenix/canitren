# 🚅 Canitren — Radar de Plazas para Perros en Alta Velocidad (Renfe)

> **Canitren** te permite conocer en tiempo real si quedan plazas disponibles para perros grandes (10 a 40 kg) en trenes **AVE, Avlo y Alvia** de Renfe, **sin tener que rellenar los 4 pasos del proceso de compra**.

[![Vercel Deployment](https://img.shields.io/badge/Vercel-Deployed-black?logo=vercel)](https://canitren.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ⚡ El Problema que Resuelve Canitren

Renfe permite viajar con perros grandes (10–40 kg) en trenes de alta velocidad, pero **con un límite crítico de 2 plazas por convoy (Coche 7)**.

Actualmente, el proceso en la web oficial es un calvario de ensayo y error:
1. **La trampa del icono 🐾**: En los resultados de búsqueda de Renfe, casi todos los trenes muestran la huella de perro, pero esto **solo indica que el modelo de tren admite el servicio, no que queden plazas libres**.
2. **Embudo ciego de 4 pasos**: Para saber si hay plaza libre, el usuario tiene que elegir tren, seleccionar tarifa obligatoria *Elige Estándar*, rellenar datos personales y llegar al paso de *Complementos / Extras*.
3. **Pérdida de tiempo masiva**: Si está agotado (0/2), hay que retroceder y repetir el embudo completo con cada tren y cada fecha.

**Canitren automatiza este proceso mediante radar continuo y muestra la disponibilidad real por adelantado.**

---

## 🌟 Características Principales

- 🎯 **Radar de Disponibilidad Real**: Indicadores claros para cada tren (✅ *Plaza Disponible*, ❌ *Agotado 0/2*, ⚠️ *No Admite*).
- 🧠 **Sugerencias Inteligentes**: Algoritmo que calcula automáticamente el próximo día con alta probabilidad de plazas (martes/miércoles fuera de hora punta) y permite lanzar la búsqueda con un solo clic.
- 💡 **Guía y Consejos Pro**:
  - **Regla de las 24 horas**: Bloqueo estricto del extra de perro grande en las 24h previas a la salida.
  - **Límite de 2 perros**: Cuello de botella en trenes de más de 350 plazas.
  - **Trampa del Coche en Silencio**: Incompatibilidad de la tarifa *Elige* silenciosa con mascotas.
  - **Ventana de cancelaciones (48h - 72h)**: Detección de plazas liberadas por cambios de billetes de otros viajeros.
- ⚡ **Streaming en Tiempo Real (SSE)**: Las plazas se actualizan en vivo en la pantalla a medida que el scraper explora el tren.
- 📍 **Catálogo de +1.000 Estaciones**: Integrado con la API abierta de [RadarDeTrenes](https://radardetrenes.com/api/v1).
- 🎨 **Diseño Moderno de Travel-Tech**: Estética cuidada de radar ferroviario (modo oscuro elegante, tipografía JetBrains Mono + Plus Jakarta Sans).

---

## 🚀 Despliegue e Instalación

### En Local

```bash
git clone https://github.com/lexisphoenix/canitren.git
cd canitren

# Arrancar con el script automatizado
./run.sh
```

Abre **[http://localhost:8050](http://localhost:8050)** en tu navegador.

### Despliegue en Vercel

El proyecto está configurado para Vercel Serverless mediante `api/index.py` y `vercel.json`:

```bash
npx vercel --prod
```

---

## 🏗️ Arquitectura Técnica

- **Frontend**: Single-Page App (SPA) responsive en vanilla HTML/CSS/JS con cliente EventSource y sugerencias algorítmicas de fechas.
- **Backend**: FastAPI (Python 3.9+) con soporte para Server-Sent Events (SSE).
- **Scraper Motor**: Playwright con emulación stealth y selectores optimizados para `venta.renfe.com`.
- **Datos Ferroviarios**: Integración con la API pública de RadarDeTrenes y endpoints DWR de Renfe.
- **Caché**: Capa en memoria con TTL de 15 minutos para minimizar peticiones redundantes.

---

## 📖 Documentación e Investigación

- 📋 [**Guía Técnica e Investigación Completa**](docs/INVESTIGATION.md) — Análisis detallado del protocolo de billetes de Renfe, ingeniería inversa y caso de estudio Madrid - Sevilla.
