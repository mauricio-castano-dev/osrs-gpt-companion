# Mantenimiento del proyecto

- Mantén README.md actualizado cuando cambien la instalación, configuración,
  comandos, herramientas o capacidades disponibles.
- Registra cambios relevantes en CHANGELOG.md. Distingue funcionalidad actual
  de propuestas pendientes; no describas la hoja de ruta como implementada.
- Nunca añadas credenciales, archivos reales de personajes, memorias SQLite,
  entornos virtuales ni copias de seguridad al repositorio.
- Usa datos ficticios en ejemplos y pruebas.
- Ejecuta las pruebas relevantes antes de publicar cambios. La suite completa
  es `python -m unittest -v` en Windows; DPAPI requiere el perfil del usuario.
- Mantén el protocolo SIWC: Responses API, store=false, stream=true, funciones
  en namespaces y resultados mediante function_call_output/call_id.
- Las acciones con efectos locales se ejecutan solo tras completar la respuesta
  del modelo y validar el nombre de herramienta y sus argumentos.
