# 🚅 Patas al Tren — Radar de Plazas para Perros en Alta Velocidad (Renfe)

> **Patas al Tren** te permite conocer en tiempo real si quedan plazas disponibles para perros grandes (10 a 40 kg) en trenes **AVE** de Renfe, **incluso antes de lanzar una búsqueda y sin pasar por los 4 pasos del proceso de compra**.

[![Vercel Deployment](https://img.shields.io/badge/Vercel-Deployed-black?logo=vercel)](https://canitren.vercel.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ⚡ El Problema que Resuelve Patas al Tren

Renfe permite viajar con perros grandes (10–40 kg) en trenes de alta velocidad, pero **con un límite crítico de 2 plazas por convoy (Coche 7)**.

Actualmente, el proceso en la web oficial es un calvario de ensayo y error:
1. **La trampa del icono 🐾**: En los resultados de búsqueda de Renfe, casi todos los trenes muestran la huella de perro, pero esto **solo indica que el modelo de tren admite el servicio, no que queden plazas libres**.
2. **Embudo ciego de 4 pasos**: Para saber si hay plaza libre, el usuario tiene que elegir tren, seleccionar tarifa obligatoria *Elige Estándar*, rellenar datos personales y llegar al paso de *Complementos / Extras*.
3. **Pérdida de tiempo masiva**: Si está agotado (0/2), hay que retroceder y repetir el embudo completo con cada tren y cada fecha.

**Patas al Tren revoluciona esta experiencia mostrando los trenes confirmados con plazas libres en portada antes incluso de escribir un origen o destino.**

---

## 🌟 Características Principales

- 📡 **Radar en Portada (Pre-Búsqueda)**: Consulta inmediatamente en la página principal los trenes verificados con plazas libres en los corredores más transitados (*Madrid–Sevilla*, *Madrid–Barcelona*, *Madrid–Málaga*, *Madrid–Valencia*).
- 🎨 **Diseño Minimalista Estilo Tesla**: Interfaz luminosa, limpia, espaciosa y sin recargar, cuidando la tipografía y la claridad visual sin estridencias.
- 🐶 **Identidad y Logo Minimalista**: Icono vectorial limpio que fusiona la aerodinámica del AVE con la silueta canina.
- 🎯 **Buscador Directo a Medida**: Comprueba cualquier par de estaciones y fecha con autocompletado inteligente de más de 1.000 estaciones.
- ⚡ **Streaming en Tiempo Real (SSE)**: Las plazas se actualizan en vivo en la pantalla mediante Server-Sent Events.
- 🤖 **Escáner Periódico Automatizado**: Script de automatización en segundo plano (`backend/scripts/radar_scanner.py`) para monitorizar periódicamente los corredores clave y mantener el feed siempre actualizado.
- 💡 **Consejos Pro de Disponibilidad**:
  - **Regla de las 24 horas**: Bloqueo estricto del extra de perro grande en las 24h previas a la salida.
  - **Límite de 2 perros**: Cuello de botella en trenes de más de 350 plazas.
  - **Trampa del Coche en Silencio**: Incompatibilidad de la tarifa *Elige* silenciosa con mascotas.
  - **Ventana de cancelaciones (48h - 72h)**: Detección de plazas liberadas por cambios de billetes.

---

## 🚀 Despliegue e Instalación

### En Local

```bash
git clone https://github.com/lexisphoenix/canitren.git
cd canitren

# Arrancar el servidor web
./run.sh
```

Abre **[http://localhost:8050](http://localhost:8050)** en tu navegador.

### Ejecutar el Escáner Periódico

```bash
# Escaneo de prueba rápido
./venv/bin/python backend/scripts/radar_scanner.py --mock

# Escaneo automatizado con navegador Playwright (modo headless)
./venv/bin/python backend/scripts/radar_scanner.py
```

### Despliegue en Vercel

```bash
npx vercel --prod
```

Web en producción: **[https://canitren.vercel.app](https://canitren.vercel.app)**

---

## 📄 Licencia

MIT License © 2026 Patas al Tren
