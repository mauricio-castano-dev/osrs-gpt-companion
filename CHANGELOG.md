# Historial de cambios

## 0.4.1 — 2026-11-10

### Añadido

- Pestaña Equipo & Progreso con equipo ocupado, ofertas GE, Slayer, misiones, Combat Achievements y KC.
- `busy` y `active_tools` en `/api/status`, protegidos por un lock independiente para permitir polling durante una respuesta.
- Indicador del chat que muestra herramientas ya ejecutadas; limpieza al terminar, fallar o limpiar historial.
- Listas y encabezados Markdown con nodos DOM seguros, sin párrafos vacíos redundantes y preservando bloques de código.
- Navegación de las tres pestañas mediante teclado, pruebas de progreso concurrente y siete pruebas JavaScript de renderizado seguro.

### Corregido

- Eliminada la instrucción contradictoria de SYSTEM que pedía comprobar nombres de timestamps; la validación del estado es interna.

### Conservado

- `auth.py`, `state_monitor.py`, `tools.py`, `wiki_client.py`, `memory_db.py` y `launcher.py` intactos.
- CSP, CSRF, loopback, construcción segura de nodos DOM y protocolo SIWC sin cambios.


## 0.4.0 — 2026-11-09

### Añadido

- Interfaz local de estilo OSRS con HUD actualizado cada tres segundos, skills, farming, birdhouses, chat y gestión de memorias.
- API loopback con validación Host/Origin, CSRF por sesión, respuestas sin caché y chat serializado.
- Chips de herramientas y pies discretos de tiempo relativo en UI y consola.
- Empaquetado editable con `osrs-companion` y `osrs-companion-ui`; UI por defecto, `--cli`, `--ui` y `--port`.
- Instalador idempotente `--install-path` que genera lanzadores absolutos y añade un directorio bin al PATH del usuario Windows.
- Pruebas de endpoints, origen/CSRF, puertos ocupados, tiempos relativos y lanzadores.

### Cambiado

- Instrucciones del agente para contestar de forma concisa y no recitar timestamps salvo petición explícita o estado no disponible.
- El respaldo entre las dos rutas históricas de estado elige el archivo más reciente por `st_mtime_ns`; la ruta explícita o guardada conserva su prioridad.
- `patches_propuestos.md` y lanzadores generados con rutas personales excluidos de Git.
- README sincronizados en español, inglés y portugués de Brasil, y exportación local del código actualizada.


## 0.3.0 — 2026-11-09

### Añadido

- `list_memories(limit=20)` y `delete_memory(memory_id)` con validación estricta de enteros y SQL parametrizado.
- Comandos locales `/estado`, `/memorias` y `/olvidar ID`, sin inferencias ni entradas en el historial del modelo.
- Persistencia atómica de la ruta válida del personaje y el modelo seleccionado en `.auth/settings.json`.
- Precedencia CLI > preferencias guardadas > valores de respaldo, con recuperación ante configuración corrupta o rutas/modelos no disponibles.
- Visibilidad del nombre validado de cada herramienta y callback opcional `on_tool_call(tool_name, ok_status)` en `answer`.
- Pruebas de comandos locales, ciclo de vida de memorias, preferencias de inicio, callbacks y compatibilidad.

### Conservado

- `auth.py`, `state_monitor.py`, `tools.py` y `wiki_client.py` sin cambios.
- Siete herramientas y protocolo SIWC intactos; el callback es local y no modifica el payload de Responses.
- La interfaz continúa siendo de consola; no incluye todavía API local ni GUI.


## 0.2.1 — 2026-11-09

### Corregido

- Farming selecciona parches activos antes de limitar a 25; informa activos, vacíos omitidos y total de parches.
- Birdhouses estructuradas pequeñas se conservan completas; fixtures y formatos anteriores siguen siendo compatibles.
- Extractos de wiki resuelven redirecciones y amplían introducciones menores de 250 caracteres con las primeras secciones, sin superar 2.500 bytes.

### Añadido

- Mundo y quick prayers; oraciones desbloqueadas y resúmenes de KC, actividades, minijuegos, POH, transporte y ubicación entre los extras de estadísticas.
- Hasta ocho ofertas personales del Grand Exchange en consultas de banco/all.
- Categoría `combat_achievements`: resumen por tier y hasta 25 tareas filtradas, nunca el catálogo completo.
- Pruebas adicionales con fixtures estructurados como Character Snapshot y documentación sincronizada en tres idiomas.

### Conservado

- `auth.py` e `inference.py` sin modificaciones; siete herramientas y protocolo SIWC intactos.


## 0.2.0 — 2026-11-09

### Añadido

- Siete herramientas en el namespace `osrs`: estadísticas, objetos, misiones/diarios, precios, wiki y dos funciones de memoria.
- Consultas granulares sobre la caché RAM con metadatos de actualización y errores sin datos antiguos.
- Banco limitado a 30 coincidencias, misiones a 40 y tareas de diarios a 30 por región.
- Resumen de liquidez en Coins y Platinum tokens, inventario y equipo.
- Precios mediante la API de OSRS Wiki, con hasta cinco coincidencias y mapping en RAM durante seis horas.
- Búsqueda de OSRS Wiki con tres enlaces e introducción en texto plano, acotada a unos 2.5 KB.
- Cliente HTTP público separado de la sesión de OpenAI y con User-Agent descriptivo.
- Pruebas de filtros sobre bancos grandes, las siete rutas, esquemas, caché, APIs y errores.

### Cambiado

- Eliminada la herramienta que enviaba el JSON completo al modelo; `snapshot()` se conserva solo para uso local.
- FTS5 tokeniza las consultas Unicode, busca con AND y usa OR si no hay resultados; mantiene deduplicación y límite de ocho memorias.
- El agente consulta precios antes de estimarlos y verifica mecánicas/requisitos en la wiki cuando necesita información externa.
- README en español, inglés y portugués de Brasil sincronizados con las nuevas capacidades.

### Conservado

- `auth.py` sin modificaciones.
- Lógica de `sse_events`, `response_round` y `answer` intacta, incluidos límites de rondas y llamadas.


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
