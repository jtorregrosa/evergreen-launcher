# Revisión de rendimiento de Evergreen y backlog para dispositivos antiguos o con pocos recursos

## Contexto

- Repositorio: Evergreen Launcher, en esta carpeta, rama `perf/android10`.
  - Es un fork de Lawnchair 15 (tag `v15.0.0-beta3.0`), basado a su vez en AOSP Launcher3 con Quickstep.
  - El código propio de Lawnchair está en `lawnchair/src/app/lawnchair`.
  - El de AOSP está en `src/`, `quickstep/src`, `systemUI/` y `wmshell/`.
  - Las librerías de iconos están en `platform_frameworks_libs_systemui/` (por ejemplo, `iconloaderlib`).
- Dispositivo objetivo: tablet antigua con Android 10 (API 29).
  - CPU de gama baja, 2-3 GB de RAM, almacenamiento eMMC.
  - Pantalla grande, por lo que hay muchos iconos visibles a la vez.
  - El objetivo secundario es cualquier dispositivo con API 26-30 o con `ActivityManager.isLowRamDevice()`.
- Restricciones de API 29 que hay que tener en cuenta:
  - No existe `RenderEffect` ni el desenfoque de ventanas (`BlurUtils`/`DepthController` requieren R o superior).
  - El modelo de compilación de ART depende de que se instale un perfil, porque el APK no viene de Play.
  - Quickstep se activa con `QUICKSTEP_MIN_SDK = 29`.
- Punto de partida: `PERF_ANDROID10.md` contiene una auditoría previa (unos 30 hallazgos con fichero y línea).
  - Úsala como semilla, pero **verifica cada hallazgo contra el código actual** antes de pasarlo al backlog.
  - Descarta o corrige los que no se sostengan.

## Objetivo

Hacer una revisión exhaustiva, **solo de lectura (no edites código)**, y producir un backlog priorizado y accionable de mejoras de rendimiento para este perfil de dispositivo.

El backlog tiene dos destinos:
- convertirse en issues de GitHub;
- implementarse en PRs pequeños, cada uno medible por separado.

## Cómo trabajar

### Fase 1. Revisión en paralelo con subagentes

Lanza en un solo mensaje un subagente `Explore` por cada área de la tabla, con la exhaustividad "very thorough". El prompt de cada subagente debe incluir:
- el contexto de arriba;
- su área y las preguntas guía;
- la regla de evidencia;
- el formato de hallazgo.

Ningún subagente edita ficheros.

| Área | Preguntas guía |
|------|----------------|
| A. Arranque en frío y proceso | Qué se ejecuta en `MainProcessInitializer`, `LawnchairApp`, `LauncherAppState`, `LawnchairLauncher.onCreate`/`onResume`, `LoaderTask` y en los providers. Qué es trabajo anticipado que podría ser perezoso. Si el baseline profile y ProfileInstaller llegan realmente a ART. |
| B. Hilo principal y almacenamiento | Usos de `firstBlocking`/`runBlocking`/`setBlocking` y de SharedPreferences, DataStore, Room y ficheros en el hilo principal. Con qué frecuencia se llama a cada uno: arranque, por frame, por toque o por icono. Llamadas binder síncronas (PackageManager, AppWidgetManager, ShortcutManager…). |
| C. Iconos y paquetes de iconos | Validez e invalidación de la caché de iconos, parseo de `appfilter`, iconos temáticos, sombras y blur por software, tamaño de bitmaps, hilos implicados, iconos de reloj y receivers que fuerzan actualizaciones. |
| D. Cajón, escritorio y scroll | Configuración de RecyclerView (pool, prefetch, `setHasFixedSize`), reciclado de carpetas y categorías, overdraw en tablet, coste de `onDraw`/`onLayout` en `BubbleTextView`/`CellLayout`/`Workspace`, asignaciones de memoria por frame, coste de arrastrar y reordenar. |
| E. Búsqueda | Hilos, debounce y cancelación, coste del fuzzy matching, proveedores (apps, contactos, ficheros, ajustes, web, calculadora) y si alguno bloquea los resultados de apps, IPC y consultas MediaStore por cada pulsación. |
| F. Animaciones, transiciones y Quickstep en API 29 | Capas por software (`setLayerType`), propiedades que provocan layout durante las animaciones, animaciones de cierre de apps, recientes y QuickSwitch en 29, `DepthController`, springs, widgets que se animan. |
| G. Memoria y bajo consumo de RAM | Comportamiento en `onTrimMemory`/`onLowMemory`, tamaño de las cachés (iconos, widgets, previews, fuentes), retención de vistas y fugas (listeners que no se desregistran), coste de recrear tras una muerte por poca memoria, uso de `isLowRamDevice`. |
| H. Trabajo en segundo plano y batería | Receivers dinámicos y su frecuencia (TIME_TICK, cambios de paquete…), WorkManager y alarmas, smartspace, tiempo y feed, peticiones de red (`lawnchair.app`, GitHub, sugerencias web), wakeups. |
| I. Build y empaquetado | R8 y minify en release, reglas de proguard, `profileinstaller`, `baselineProfiles` por variante, `debuggable`/`profileable`, recursos y ABIs, `coreLibraryDesugaring`, uso de Compose fuera de los ajustes. |

**Regla de evidencia.** Cada hallazgo debe citar `ruta:línea` y un extracto breve que el subagente haya leído de verdad. Si la conclusión depende de comportamiento en tiempo de ejecución que no se puede ver en el código, márcalo como `HIPÓTESIS` y di qué medición lo confirmaría. Nada de hallazgos genéricos del tipo "usar coroutines".

**Formato de hallazgo de cada subagente** (devolver como máximo unos 1200 palabras):
```
- id: <ÁREA>-<n>
  título: <una línea>
  evidencia: <ruta:línea> — <extracto o descripción precisa>
  frecuencia: arranque | por frame | por toque | por pulsación | por icono | periódica | rara
  por qué duele en API 29 / poca RAM: <mecanismo concreto>
  propuesta: <cambio concreto>
  impacto: alto | medio | bajo   riesgo: alto | medio | bajo   esfuerzo: S | M | L
  estado: CONFIRMADO | HIPÓTESIS
```

### Fase 2. Verificación adversarial

Cuando vuelvan los subagentes:

1. **Deduplica.** Junta los hallazgos repetidos entre áreas, sobre todo los de B, que aparecen en casi todas.
2. **Verifica.** Para cada hallazgo de impacto alto o medio, lanza un subagente verificador por grupo de unos 5 hallazgos. Su encargo es intentar **refutarlos** leyendo el código:
   - ¿la ruta se ejecuta de verdad?
   - ¿la frecuencia es la que se dice?
   - ¿hay ya una caché o una guarda que lo evita?

   Su veredicto debe ser `CONFIRMADO`, `REFUTADO` o `HIPÓTESIS`, con su propia cita.
3. **Descarta** los refutados y anota por qué en una sección aparte.
4. **Comprueba los valores por defecto.** Para cada hallazgo, mira el valor por defecto del ajuste implicado (por ejemplo, en `lawnchair/res/values/config.xml`). No es lo mismo un problema que afecta a todos los usuarios que uno que solo afecta a quien activa una opción.

### Fase 3. Backlog

Escribe `docs/perf/BACKLOG.md` (y opcionalmente `docs/perf/backlog.csv` para importar como issues) en español, con esta estructura.

1. **Resumen.** Unas 10 líneas con los 5 problemas de más peso y el orden de ataque recomendado.
2. **Épicas.**
   - EVG-E1: Arranque en frío.
   - EVG-E2: Hilo principal y almacenamiento.
   - EVG-E3: Iconos.
   - EVG-E4: Fluidez del cajón y del escritorio.
   - EVG-E5: Búsqueda.
   - EVG-E6: Animaciones.
   - EVG-E7: Memoria y bajo consumo de RAM.
   - EVG-E8: Segundo plano y batería.
   - EVG-E9: Build y perfiles.
   - EVG-E10: Modo "dispositivo modesto". Es un conjunto de valores por defecto que se aplican cuando `isLowRamDevice` es cierto o el SDK es menor de 31, configurable desde los ajustes.
3. **Ítems.** Una tabla por épica, ordenada por prioridad = impacto / (riesgo × esfuerzo). Cada ítem lleva:
   - `ID` (EVG-123), título, épica, prioridad P0-P3, impacto, riesgo, esfuerzo S/M/L;
   - evidencia (`ruta:línea`) y estado (CONFIRMADO/HIPÓTESIS);
   - **propuesta técnica** concreta;
   - **criterio de aceptación medible**, por ejemplo "TotalTime de `am start -W` −20 % en frío en estado `verify`" o "0 llamadas `firstBlocking` en `updateHeaderScroll`";
   - **cómo medirlo** (comando exacto);
   - dependencias entre ítems y si cambia algo visible o algún valor por defecto (y, en ese caso, si va detrás del modo "dispositivo modesto").
4. **Ganancias rápidas.** Ítems P0/P1 con esfuerzo S y riesgo bajo, pensados para el primer PR.
5. **Plan de medición base.** Lo que hay que medir antes de tocar nada en la tablet:
   - `am start -W` en los estados de compilación `verify` y `speed-profile`;
   - Perfetto en Android 10 (`setprop persist.traced.enable 1`) con las categorías y los escenarios concretos;
   - `dumpsys gfxinfo` con swipes automatizados;
   - overdraw;
   - `meminfo` y `am_proc_died`.

   Siempre con un APK release que tenga `profileable`, nunca con uno debug. Indica qué métricas registrar en una tabla de referencia.
6. **Descartados.** Los hallazgos refutados y el motivo.
7. **Riesgos y cosas que no se deben tocar.** Por ejemplo, divergencias con AOSP que complicarían traer arreglos de la rama 15, y cambios de aspecto visibles.

## Reglas

- No edites código ni hagas commits. El único fichero que puedes escribir es el backlog, en `docs/perf/`.
- Distingue en todo momento CONFIRMADO de HIPÓTESIS, y no infles el impacto sin evidencia.
- Prioriza los cambios pequeños, aislados y reversibles. Cada ítem debe caber en un PR.
- Si algo solo se puede decidir midiendo, conviértelo en un ítem de medición (EVG-Mx) en lugar de suponer el resultado.
- Al terminar, dame en el chat:
  - el resumen;
  - las 5 primeras ganancias rápidas;
  - cuántos hallazgos se confirmaron, cuántos se refutaron y cuántos quedaron como hipótesis.
