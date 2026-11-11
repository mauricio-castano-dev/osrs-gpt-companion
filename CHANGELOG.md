# Historial de cambios

## 0.5.0 — 2026-11-10

### Añadido

- Tema Obsidian Runic Slate & Amber Gold con tipografía Pixelify Sans/Chakra Petch/Plus Jakarta Sans, alternativas del sistema, paneles biselados y diseño adaptable con movimiento reducido.
- 39 sprites SVG originales en CSS, incluyendo las 24 habilidades, recursos y slots de equipo; `data-skill`, `.skill-max` e iconografía para las siete herramientas.
- Explorador de progreso situado tras el banco, con cuatro botones de filtro inmediato y estados de misión coloreados.
- Respaldo en memoria del navegador tras fallos de `/api/progress`, marcado como parcial y con edad del reporte; solo utiliza el subconjunto previamente recibido por `/api/status`.
- Tres pruebas Python nuevas y siete casos DOM nuevos: 79 pruebas Python y 25 casos DOM en total. Comprobación visual con datos ficticios en escritorio y pantalla estrecha.
- README sincronizados en tres idiomas y exportación local del código actualizada.

### Corregido

- Las categorías vacías no muestran encabezados redundantes junto a resultados de otra categoría.
- Rechazos HTTP 403 con cuerpos pequeños: se descartan bytes de forma acotada antes de cerrar para evitar reinicios intermitentes de conexión en Windows; las validaciones y el bloqueo de mutaciones siguen activos.

### Seguridad y compatibilidad

- CSP ampliada exclusivamente para estilos/fuentes de Google Fonts y sprites `data:`; sin scripts externos ni `unsafe-inline`.
- Loopback, Host, Origin, Sec-Fetch-Site, CSRF y `Cache-Control: no-store` conservados.
- `auth.py`, `state_monitor.py`, `tools.py`, `wiki_client.py`, `memory_db.py`, `inference.py` y `launcher.py` intactos; protocolo SIWC sin cambios.

## 0.4.3 — 2026-11-10

### Añadido

- `GET /api/progress` con búsqueda, categoría y estado validados; consulta en RAM sin inferencia ni cambios del historial.
- Explorador de misiones, Achievement Diaries y Combat Achievements en Equipo & Progreso, con debounce de 180 ms, selectores inmediatos y descarte de respuestas fuera de orden.
- Resumen de tiers de diarios por región; limpieza al quedar indisponible la instantánea.
- Resultados con estados, cantidades y avisos de truncamiento (40 misiones, 30 tareas por diario, 25 tareas de combate), construidos con nodos DOM seguros.
- Cuatro pruebas Python y seis casos DOM nuevos: 76 pruebas Python y 18 casos DOM en total.
- README sincronizados en tres idiomas y exportación local del código actualizada.

### Conservado

- Los siete módulos protegidos, el protocolo SIWC, las validaciones HTTP y CSP/CSRF permanecen sin cambios.
- Los detalles de tareas de combate siguen requiriendo texto de búsqueda; `in_progress` aplica a misiones.

## 0.4.2 — 2026-11-10

### Añadido

- Buscador de banco e inventario en RAM con debounce de 180 ms, límite de 100 caracteres, 30 resultados del banco y descarte de respuestas atrasadas; no utiliza inferencia.
- `GET /api/bank`, `GET /api/models` y `POST /api/model`, con catálogo cacheado por sesión, validación de slugs, CSRF y bloqueo durante una respuesta.
- Selector de modelo en el chat con persistencia en `.auth/settings.json`; si falla la escritura, se mantiene el modelo anterior. Catálogo inaccesible: selector oculto sin error intrusivo.
- Polling de estado cada 600 ms durante el turno, limpiado siempre al terminar o fallar.
- Cinco pruebas Python nuevas y cinco pruebas JavaScript nuevas (12 casos DOM en total).
- README sincronizados en tres idiomas y exportación local del código actualizada.

### Conservado

- `auth.py`, `state_monitor.py`, `tools.py`, `wiki_client.py`, `memory_db.py`, `inference.py` y `launcher.py` intactos.
- CSP estricta, CSRF/origen, creación segura de nodos DOM y protocolo SIWC.

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
