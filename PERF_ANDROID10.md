# Lawnchair 15 beta3: rendimiento en tablet Android 10 (API 29)

Este es un análisis estático: hemos leído el código, pero todavía no hemos medido nada. Las rutas se dan respecto a la raíz del repositorio. Las marcas (?) indican cosas que hay que confirmar en el dispositivo.

Escalas usadas:
- **Impacto**: lo que se espera ganar en esa tablet.
- **Riesgo**: probabilidad de regresiones o de que se note un cambio de comportamiento.

## Nivel 1: impacto alto, riesgo bajo (empezar por aquí)

| # | Área | Problema | Dónde | Propuesta | Imp. | Riesgo |
|---|------|----------|-------|-----------|------|--------|
| 1 | Iconos y arranque | El ajuste `alwaysReloadIcons` viene activado por defecto. Hace `reloadIcons()` en cada `onCreate`, lo que vacía la BD de iconos y la caché y obliga a renderizar de nuevo todos los iconos (paquete, normalizador, sombra por software y escritura en la BD). Además ocurre en cada muerte por poca memoria. La KDoc dice "si hay un icon pack activo", pero el código no lo comprueba. | `lawnchair/res/values/config.xml:110`, `LawnchairLauncher.kt:252,498` | Poner el valor por defecto a `false` o condicionarlo a que haya un icon pack cuya versión haya cambiado. | Muy alto | Bajo |
| 2 | Iconos | `ACTION_TIME_TICK`: cada minuto lanza un `onAppIconChanged` por cada reloj del icon pack y por cada usuario. Cada llamada supone un `PackageUpdatedTask` (renderizado, IPC y rebind). Los relojes ya se animan solos con `ClockDrawableWrapper`. | `icons/LawnchairIconProvider.kt:310-326` | Escuchar solo `TIMEZONE`, `TIME_CHANGED` y `DATE_CHANGED`. | Alto (con pack) | Bajo |
| 3 | Arranque | La BD Room se abre y se hacen 3 `wal_checkpoint(full)` con `runBlocking` en el hilo principal en cada `onCreate`. Cada uno hace fsync en una eMMC lenta. | `LawnchairLauncher.kt:254`, `data/AppDatabase.kt:34` | Hacerlo en `Dispatchers.IO` desde `onStop`, o solo antes de una copia de seguridad. | Alto | Bajo |
| 4 | Arranque | El baseline profile no se instala. `InitializationProvider` se elimina en el manifest, así que `ProfileInstallerInitializer` nunca se ejecuta, y nada llama a `ProfileInstaller`. Además, el perfil está en `src/lawnWithQuickstepRelease/`, una carpeta sin la dimensión channel (?, quizá no se empaqueta). Por último, `baseline-profile` apunta a `app.lawnchair`. | `AndroidManifest-common.xml:188`, `baseline-profile/.../Constants.kt:4` | Llamar a `ProfileInstaller.writeProfile()` en segundo plano unos 5 s después del primer frame, comprobar que el APK contiene `assets/dexopt/baseline.prof` y corregir el paquete. | Alto | Bajo |
| 5 | Búsqueda | La búsqueda "solo apps" calcula los resultados en `Dispatchers.Main`: FuzzyWuzzy sobre todas las apps más la IPC `getShortcuts`, en cada pulsación. Además lee `AllAppsList` fuera del hilo del modelo. | `search/algorithms/LawnchairAppSearchAlgorithm.kt:60` | Calcular en el hilo del modelo o en `Default` y publicar solo el resultado. | Alto | Bajo |
| 6 | Búsqueda | En la búsqueda local (la opción por defecto), `combine()` espera a que todos los proveedores emitan. Las sugerencias web tardan hasta 1000 ms, así que las apps aparecen con ese retraso. | `search/algorithms/LawnchairLocalSearchAlgorithm.kt:70-87`, `config.xml:169` | Emitir las apps y la calculadora en cuanto estén y combinar después el resto (`merge`/`scan` o `onStart{emit(empty)}`). | Alto (percibido) | Bajo |
| 7 | Búsqueda | No hay debounce: se encola un `ModelUpdateTask` por cada pulsación y las búsquedas obsoletas no se cancelan. Cada pulsación hace además unas 4 o más lecturas `firstBlocking` de DataStore y dos IPC sin caché (`resolveMarketSearchActivity`). | `AllAppsSearchBarController.java:103`, `AppSearchProvider.kt:17-20`, `SearchTargetFactory.kt:533` | Debounce de 100-150 ms con `collectLatest` o número de secuencia, preferencias en caché y componente del market en caché. | Alto | Bajo |
| 8 | Animaciones | La animación "suck-in" al cerrar una app (opción por defecto) usa una vista a pantalla completa con `LAYER_TYPE_SOFTWARE`. Anima escala, traslación y alfa y crea un `ViewOutlineProvider` nuevo en cada frame. Se activa sin QuickSwitch (?, comprobar si pasa en la tablet). | `views/FullScreenOverlayView.kt:41,86-91` | Usar capa `HARDWARE` o ninguna y reutilizar el outline. En dispositivos con poca RAM, usar `fade_in` por defecto. | Alto | Bajo |
| 9 | Hilo principal | Se usa `firstBlocking()` (`runBlocking { flow.first() }`) en rutas calientes: `updateHeaderScroll` en cada evento de scroll del cajón (3 lecturas y parseo JSON del color), `CellLayout.isOccupied` en los bucles de reordenación, `Workspace.onInterceptTouchEvent`, `PagedView` en el fling y `BubbleTextView.shouldTextBeVisible`. | `ActivityAllAppsContainerView.java:807,834,842`, `CellLayout.java:1866,1949`, `Workspace.java:1211`, `BubbleTextView.java:866` | Guardar los valores en campos que se actualicen con `onEach`/`StateFlow` (`LawnchairScrimView` ya sigue ese patrón). | Medio-alto | Bajo |

## Nivel 2: impacto alto o medio, riesgo medio

| # | Área | Problema | Dónde | Propuesta | Imp. | Riesgo |
|---|------|----------|-------|-----------|------|--------|
| 10 | Arranque y prefs | `PreferenceManager2.init` hace `iconShape.firstBlocking()`, el primer acceso a DataStore: lee y parsea el fichero completo y comprueba la migración, todo en el hilo principal. `getRemoteDefault()` lee una segunda DataStore y crea un `Json{}` nuevo, dos veces. `QsbSearchProvider.resolveDefault` hace N IPC de forma anticipada. | `preferences2/PreferenceManager2.kt:224,504,742,786` | Calentar DataStore en segundo plano desde el inicializador de proceso y hacer perezosos los valores por defecto remotos y el QSB. | Alto | Medio |
| 11 | Arranque y prefs | Hay unas 22 llamadas `firstBlocking` por cada `DeviceProfile` (11 en `DeviceProfile` y 11 en `DeviceProfileOverrides`), y el IDP construye varios en el hilo principal. | `DeviceProfile.java`, `DeviceProfileOverrides.kt:92-135` | Leer una instantánea de las prefs una sola vez y pasársela. | Medio-alto | Medio |
| 12 | Iconos | La clave de estado de la caché (`getSystemIconState`) depende de `isThemeEnabled` y `iconPackVersion`, que se rellenan de forma perezosa. `verifyIconChanged` puede ver una clave distinta al arrancar y borrar la caché entera (?). | `LawnchairIconProvider.kt:68-85,230-235` | Construir la clave a partir de las prefs o calcular el mapa al principio. Confirmarlo antes con un log. | Alto (?) | Bajo |
| 13 | Iconos | Por cada icono adaptativo se crea una segunda sombra con `BlurMaskFilter` por software y una copia ARGB completa, aunque ya lleva sombra de contorno (path shadow). | `iconloaderlib/.../BaseIconFactory.java:252-256` | Eliminar la segunda pasada, o hacerlo opcional para poca RAM. | Medio-alto | Medio (cambia el aspecto) |
| 14 | Iconos | El `appfilter.xml` se parsea en cada arranque de proceso, sin caché en disco. El primer icono bloquea el hilo del modelo hasta que termina (`loadBlocking`). `CustomIconPack` llama a `getResourcesForApplication` en el hilo principal. Los mapas no son thread-safe. El themed pack se carga aunque los iconos temáticos estén desactivados. | `icons/iconpack/CustomIconPack.kt:24,69-130`, `IconPackProvider.kt:47` | Guardar el mapa serializado con la clave versionCode+lastUpdateTime, usar `ConcurrentHashMap` y cargar el themed pack de forma perezosa. | Medio | Bajo |
| 15 | Cajón | Las carpetas del cajón se vuelven a inflar en cada bind (`removeAllViews` + `inflateFolderAndIcon`), y `Folder.bind` añade un listener cada vez, lo que provoca fuga y GC. | `allapps/BaseAllAppsAdapter.java` (caso carpeta), `Folder.java:570` | Inflar una vez por ViewHolder, crear el `Folder` al tocar y quitar el listener al reciclar. | Alto (si hay carpetas) | Medio |
| 16 | Cajón | El modo categorías hace `getPackageInfo`/`getApplicationInfo` por app y por regla en cada reconstrucción del adaptador. El modo carpetas usa un `contains` O(N·M). | `util/AppCategorizationUtils.kt:30`, `FlowerpotApps.kt:59`, `LawnchairAlphabeticalAppsList.kt:90,119` | Usar las flags de `AppInfo`, caché por paquete y `HashSet`. | Alto (si se usa) | Bajo |
| 17 | Desenfoque | El fondo desenfocado (desactivado por defecto) se construye en el constructor de `LauncherRootView`, en el hilo principal: decodifica el wallpaper a resolución completa, crea 3 bitmaps ARGB a pantalla completa e inicializa un contexto GL de HokoBlur. Además añade overdraw a pantalla completa. | `LauncherRootView.java:64-115` | Reducir a 1/4, desenfocar en segundo plano, usar un solo bitmap RGB_565 y, si se puede, ponerlo como fondo de ventana. | Alto (si se usa) | Medio |
| 18 | Cajón tablet | En tablet, el sheet opaco se dibuja encima del workspace y del wallpaper, que siguen dibujándose. En API 29 no hay blur que lo justifique (?). | `ActivityAllAppsContainerView.java:1093,1489`, `AllAppsState.java:219` | En API < 31, ocultar el workspace cuando el sheet está abierto del todo. | Medio | Medio |

## Nivel 3: impacto bajo o medio, riesgo bajo (hacerlos de paso)

- **Arranque.** `LauncherOptionsPopup.restoreMissingPopupOptions`/`migrateLegacyPreferences` hace 5 `firstBlocking` y un `setBlocking` en cada arranque (`LawnchairLauncher.kt:237`). Propuesta: hacerlo una sola vez, controlado por un flag de migración.
- **Arranque.** El overlay del feed hace `reconnect()` (IPC `resolveService`) nada más construirse (`OverlayCallbackImpl.kt:168`). Propuesta: añadir `.drop(1)`.
- **Arranque.** Smartspace consulta los widgets e inicia `HeadlessWidgetsManager` aunque el tiempo esté desactivado (`SmartspaceWidgetReader.kt:41`). Propuesta: crearlo de forma perezosa.
- **Arranque.** `LawnchairBugReporter` borra los logs en el hilo principal. `FontCache` carga en `MainScope` y `TTFFont` lee de disco en el hilo principal.
- **Iconos.** En el tema clásico de Lawnicons (v1-3), `themeMap` se recalcula en cada acceso (`LawnchairIconProvider.kt:76-79`).
- **Iconos.** `SystemIconPack` se crea de nuevo en cada llamada (`IconPackProvider.kt:22`).
- **Iconos.** Los drawables de los icon packs se decodifican a resolución completa (`CustomIconPack.kt:53`), cuando bastaría con `setTargetSize`.
- **Iconos.** `ThemedIconDrawable` infla el monocromo en cada `newIcon()` y crea un `CustomAdaptiveIconDrawable` con un bitmap que no se usa.
- **Búsqueda.** `AppMatcher` crea `Regex("\\s+")` dos veces por app y por pulsación. Propuesta: tokenizar una vez y no usar fuzzy por debajo de 3 caracteres.
- **Búsqueda.** `SettingsSearchProvider` hace reflexión en cada consulta.
- **Búsqueda.** `FileSearchProvider` hace un `LIKE '%kw%'` sin `LIMIT`, más un stat por fila.
- **Búsqueda.** La calculadora usa excepciones como control de flujo.
- **Búsqueda.** `SearchResultIcon` encola con `postAtFrontOfQueue` en `MODEL_EXECUTOR` sin caché.
- **Animación.** Al enfocar la barra de búsqueda se anima `setPadding`, lo que provoca un layout en cada frame (`AllAppsSearchInput.kt:276`).
- **Compose.** Solo se usa en `ComposeBottomSheet` (sheets transitorios). En el cajón y en el escritorio no hay riesgo de recomposición.

## Errores encontrados de paso (no son de rendimiento)

- `BaseIconCache.java:665`: en API < 33 el color se lee con `c.getInt(0)`, que es la columna `componentName` (texto). En Android 10 el color de los puntos de notificación y de los popups probablemente sale mal.
- `BaseAllAppsAdapter.java`: `VIEW_TYPE_PRIVATE_SPACE_HEADER` no tiene `break` y cae en el caso de carpeta (?).
- `LawnchairLauncher.kt:199`: `statusBarClock.get().onEach{}` no tiene `launchIn`, así que nunca se recoge.

## Qué medir en la tablet antes de tocar nada

Mide sobre un **APK release**: `./gradlew assembleLawnWithQuickstepGithubRelease`, que sin keystore se firma con la clave de debug. El APK debug es `debuggable`, ART no lo optimiza igual y los tiempos no son representativos. Para usar Perfetto o simpleperf con un release, añade `<profileable android:shell="true"/>` (disponible desde API 29).

```
PKG=io.github.jtorregrosa.evergreen   # release (en debug: io.github.jtorregrosa.evergreen.debug)
ACT=$PKG/app.lawnchair.LawnchairLauncher
```

0. **Contexto del dispositivo.** Ejecuta `adb shell getprop ro.product.model; getprop ro.config.low_ram; cat /proc/meminfo | head -3`, cuenta las apps con `adb shell pm list packages -3 | wc -l` y apunta qué icon pack y qué opciones usas. Pon Evergreen como launcher por defecto.
1. **Arranque en frío.** Repítelo unas 10 veces y quédate con la mediana:
   - `adb shell am force-stop $PKG && adb shell am start -W -n $ACT -a android.intent.action.MAIN -c android.intent.category.HOME`, anotando TotalTime y WaitTime.
   - `adb logcat -b events | grep am_activity_launch_time` y `adb logcat | grep "Displayed\|Fully drawn"`.
   - Hazlo en tres estados de compilación:
     - `adb shell cmd package compile -m verify -f $PKG`, que simula una instalación recién hecha sin perfil.
     - `-m speed-profile -f`, el caso ideal con perfil.
     - Tal como quede tras unos días de uso.
   - `adb shell dumpsys package dexopt | grep -A2 $PKG` indica qué estado tiene ahora.
2. **Tiempo hasta ver los iconos y re-renderizado de la caché.** Haz una traza de Perfetto del arranque en frío y fíjate en `LoaderTask`, los bloques `binder transaction` y la actividad del hilo `launcher-loader`. Compara con y sin icon pack, y con `alwaysReloadIcons` activado y desactivado (está en Ajustes › Iconos o en las opciones de depuración).
3. **Perfetto en Android 10.** Primero `adb shell setprop persist.traced.enable 1`. Después usa `record_android_trace` (del repositorio de Perfetto) o ui.perfetto.dev con estas categorías: `sched freq idle am wm gfx view binder_driver dalvik disk` más `-a $PKG`. Escenarios: arranque en frío, abrir el cajón, hacer scroll rápido, escribir "goo" en la búsqueda y volver a casa desde una app (animación de cierre).
4. **Fluidez del cajón y del escritorio.**
   - `adb shell dumpsys gfxinfo $PKG reset`.
   - Abre el cajón y haz 10 swipes con `adb shell input swipe 600 1500 600 300 150`.
   - `adb shell dumpsys gfxinfo $PKG`: anota Janky frames y los percentiles 50, 90, 95 y 99, y saca `framestats` si quieres el detalle por frame.
   - Repite con las carpetas o categorías del cajón activadas si las usas.
5. **Overdraw y GPU.** Usa `adb shell setprop debug.hwui.overdraw show` y `setprop debug.hwui.profile visual_bars`, reinicia el launcher y haz capturas de pantalla del escritorio, del cajón y de la búsqueda.
6. **Bloqueos del hilo principal.** En la traza de Perfetto, busca en el hilo `main` los slices de `binder transaction`, de `Lock contention` y los huecos de `runBlocking`. Si quieres, activa StrictMode en un build debug (`Launcher.java:304`).
7. **Memoria y muertes.** `adb shell dumpsys meminfo $PKG` en reposo y con el cajón abierto. Anota cuántas veces se recrea el launcher con `adb logcat -b events | grep am_proc_died` tras abrir apps pesadas, porque cada recreación paga el punto 1 de la tabla.
8. **Búsqueda.** En Perfetto, mide el tiempo entre `input` (tecla) y el frame con los resultados. Prueba la búsqueda local con y sin sugerencias web.

Haz cada medición con la versión base, que es este APK sin cambios, y después de cada bloque de mejoras. Cambia una cosa cada vez.
