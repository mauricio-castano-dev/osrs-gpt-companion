# Historial de cambios

## Documentación — 2026-11-09

- Añadidas traducciones completas al inglés y portugués de Brasil, con navegación entre idiomas.
- Español conservado como documentación principal; traducciones sincronizadas en el mantenimiento.

- Identificado **Character Snapshot** como plugin exportador de RuneLite.
- Aclarado que el usuario elige la carpeta de exportación en el plugin.
- Corregidos los ejemplos para utilizar `<nombre_del_personaje>.json` y una ruta explícita mediante `--state-file`.
- Eliminadas del README las suposiciones de una carpeta automática y un nombre de personaje fijo.

## 0.1.0 — 2026-11-09

Primera iteración del agente interactivo de OSRS.

### Incluido

- Consola Python con autenticación Sign in with ChatGPT.
- OAuth loopback, PKCE, validación de identidad y credenciales protegidas con DPAPI.
- Requests a Responses API con streaming y almacenamiento remoto deshabilitado.
- Monitor watchdog con caché en memoria y manejo de reemplazos del JSON.
- Memorias persistentes y búsqueda por frase con SQLite FTS5.
- Tres herramientas locales y ciclo de invocación con validación de argumentos.
- Límites de rondas y llamadas; protección frente a llamadas duplicadas por ID.
- Pruebas automatizadas, ejemplo ficticio y documentación de instalación.

### Corregido

- Lectura del archivo real del personaje mediante `--state-file`.
- Límite de lectura ampliado a 1 MiB.
- Compatibilidad con SSE válido cuando la conexión omite `Content-Type`.

### Pendiente

- Consulta selectiva del estado para reducir el contexto enviado al modelo.
- Fuentes web de OSRS y precios actuales.
