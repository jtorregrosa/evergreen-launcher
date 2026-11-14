# Evergreen: backlog de rendimiento para dispositivos antiguos o con pocos recursos

- **Base:** rama `perf/android10`, que es Lawnchair 15 beta3 (`v15.0.0-beta3.0`) con el renombrado a Evergreen.
- **Método:**
  1. 9 revisiones del código por área, sin modificarlo.
  2. 4 verificadores adversariales intentaron refutar los hallazgos de impacto alto y medio.
  3. Comprobaciones en la tablet real con adb.
- **Estado de cada hallazgo:**
  - **CONFIRMADO**: se ha leído el código y, cuando era posible, se ha visto en el dispositivo.
  - **HIPÓTESIS**: hace falta medirlo.
  - Los refutados están en el apartado 6.

## 0. Dispositivo de referencia (leído por adb)

| Dato | Valor |
|---|---|
| Modelo | Lenovo Tab M10 FHD Plus (TB-X606F) |
| SoC | MediaTek Helio P22T (MT8768), 8× Cortex-A53 a 2,3 y 1,8 GHz; GPU PowerVR GE8320 |
| RAM | 3,9 GB (`MemAvailable` ≈ 2,0 GB en reposo), `ro.config.low_ram` sin definir, `heapgrowthlimit` 256 MB |
| Pantalla | 1200×1920 a 240 dpi (≈ 800×1280 dp, perfil tablet) |
| Android | 10 (API 29), parche 2023-08-05 |
| Navegación | 3 botones; escala de animaciones 0,5 |
| Recientes | los proporciona el launcher de Lenovo (`com.tblenovo.launcher`), así que en Lawnchair `isRecentsEnabled = false` |
| Apps | 35 lanzables (22 de terceros); la app de Google (GSA) está instalada; Lawnicons 2.18.0 |
| Launcher actual | Lawnchair 15 beta3 (el mismo código base), `speed-profile` por bg-dexopt |
| dexopt | `pm.dexopt.install` y `bg-dexopt` = `speed-profile` |

**Mediciones base (Lawnchair 15 beta3 de serie, el mismo código que Evergreen sin cambios):**
- **Arranque `am start -W`:** `TotalTime` de 2245 a 2402 ms, con una mediana de unos **2,32 s** (6 muestras válidas, estado `speed-profile`).
  - Aviso: tras un `force-stop`, el sistema relanza la pantalla de inicio por su cuenta y una de cada dos mediciones devuelve 0. Hay que usar el script del apartado 5.
- **Iconos:** en cada arranque en frío salen entre **15 y 30** líneas `Database bulk icon loading failed, using fallback` en logcat, una por cada icono del escritorio o dock que se vuelve a renderizar. La causa real es **EVG-3b**: la escritura de las opciones del popup recarga la cuadrícula y eso borra la BD de iconos. Ya está arreglado y el contador baja a 0.
- **Memoria:** el launcher en primer plano ocupa unos 187 MB de PSS (Java 22 MB, nativo 30 MB). En segundo plano llegó a tener 152 MB en swap (zram).
- **Widgets:** el `AppWidgetHost` 1028 (widgets sin cabeza de Smartspace y la barra de búsqueda) sigue escuchando con la pantalla apagada (`dumpsys appwidget`). Confirma EVG-12 en el dispositivo.
- **Feed:** con el launcher en primer plano no se vio ningún bind a GSA. EVG-14 queda en HIPÓTESIS para este dispositivo.

## 1. Resumen

1. **La caché de iconos no sirve.**
   - `alwaysReloadIcons=true` (el valor por defecto) borra la BD y la caché en memoria en cada `onCreate` y reinicia el loader recién lanzado. Todos los iconos se vuelven a renderizar en cada arranque y cada vez que el sistema mata el launcher por falta de memoria. Está confirmado en logcat.
   - Debajo hay dos bugs que quedan al descubierto al quitarlo:
     - el icono en alta resolución se lee de la columna equivocada (`getBlob(2)`);
     - en API < 33 el color se lee de la columna equivocada.
   - Los tres van en el **mismo PR**: si solo se quita la recarga, se sigue renderizando en silencio.
2. **El arranque bloquea el hilo principal:**
   - abre Room y hace 3 `wal_checkpoint(full)` con `runBlocking`;
   - lee en frío 2 DataStores;
   - hace más de 60 `firstBlocking`.
3. **R8 está casi desactivado:** hay un `-dontoptimize` global y `-keep class com.android.** { *; }`. Además el baseline profile está en un source set que no usa ninguna variante, y ProfileInstaller no se ejecuta nunca. Las primeras horas o días tras cada instalación corren interpretadas o en JIT.
4. **Se lee DataStore de forma bloqueante en cada frame o medición:**
   - al pasar páginas, unas 4 lecturas por frame;
   - al hacer scroll del cajón, 3 por evento;
   - en cada `BubbleTextView.onMeasure`.
5. **La búsqueda espera a la red:** `combine()` retiene los resultados de apps hasta 1 s esperando las sugerencias web (activas por defecto), y no hay debounce.
6. **Hay trabajo con la pantalla de inicio invisible:** widgets sin cabeza, batería y NowPlaying de Smartspace. Además, hay scopes de corrutinas que nunca se cancelan y retienen la Activity anterior en cada `recreate()`.

**Orden de ataque:**
1. EVG-0x (instrumentación para poder medir).
2. EVG-1 (iconos).
3. EVG-2 y EVG-3 (arranque).
4. EVG-4 (perfil) y EVG-5 (R8).
5. EVG-6 (preferencias en rutas calientes).
6. EVG-9 y EVG-10 (búsqueda).
7. EVG-12, EVG-13 y EVG-15 (segundo plano y fugas).
8. Después, la épica E10 (modo "dispositivo modesto").

## 2. Ganancias rápidas (primeros PRs: P0/P1, esfuerzo S, riesgo bajo)

| Orden | ID | Qué | Por qué primero |
|---|---|---|---|
| 1 | EVG-01 + EVG-02 | `reportFullyDrawn` + release `profileable` | Hacen falta para poder medir lo demás |
| 2 | EVG-1 | Caché de iconos: recarga por defecto desactivada, más C-1 y C-2 | Es el mayor coste de arranque confirmado en el dispositivo |
| 3 | EVG-2 | Quitar el checkpoint de Room del hilo principal | Bloqueo seguro antes del primer frame |
| 4 | EVG-4 | Empaquetar el baseline profile y ejecutar ProfileInstaller | Código AOT desde la instalación |
| 5 | EVG-6a | Cachear las preferencias de `Workspace`, `PageIndicatorDots`, `updateHeaderScroll` y `BubbleTextView` | Jank por frame, con cambios de pocas líneas |
| 6 | EVG-9 | Búsqueda: mostrar primero los resultados locales y añadir debounce a la web | La latencia que más se nota |
| 7 | EVG-16 | Quitar la NPE en cada apertura de app | Una línea |

## 3. Épicas e ítems

Columnas: prioridad (P0-P3), impacto (I) y riesgo (R) en Alto/Medio/Bajo, esfuerzo (E) S/M/L. Las rutas son relativas a la raíz del repo.

### EVG-E0: Instrumentación (requisito previo)

| ID | P | Título | Evidencia | Propuesta | I/R/E | Aceptación y medición |
|---|---|---|---|---|---|---|
| EVG-01 | P0 | No hay `reportFullyDrawn` | grep vacío en `src`, `quickstep` y `lawnchair` | Llamarlo la primera vez que se ejecuta `QuickstepLauncher.finishBindingItems` (`QuickstepLauncher.java:1163`) | B/B/S | Aparece `Fully drawn` en logcat; TTFD medible |
| EVG-02 | P0 | El release no se puede perfilar | No hay `<profileable>` en ningún manifest | Añadir `<profileable android:shell="true"/>` (API 29+) en el release o en un build type `benchmark` | M/B/S | `perfetto` y `simpleperf` se pueden enganchar a `io.github.jtorregrosa.evergreen` |
| EVG-03 | P1 | Trazas propias | — | `Trace.beginSection` en `LoaderTask` (workspace, bind, all apps), `PreferenceManager2.<init>`, `IconPack.loadInternal`, `doSearch`→`onSearchResult` y `updateHeaderScroll` | M/B/S | Secciones visibles en Perfetto |

### EVG-E3: Iconos (la épica con más peso)

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-1 | **P0** | Recarga y borrado completo de la caché de iconos en cada `onCreate`, más 2 bugs de lectura de la BD | `lawnchair/res/values/config.xml:110` (`always_reload_icons=true`). `LawnchairLauncher.kt:252,498-503` (no comprueba que haya icon pack, aunque la KDoc lo dice). `LauncherAppState.java:237-242`. `BaseIconCache.java:187-199` (`mIconDb.clear(); mCache.clear()`). `LauncherModel.java:311-323` (reinicia el loader). Bug C-1: `BaseIconCache.java:682`, `c.getBlob(2)` sobre `icon_color`, que es INTEGER; lanza SQLiteException y el `catch` hace `return false`, con lo que se vuelve a renderizar en silencio. Bug C-2: `BaseIconCache.java:666`, `c.getInt(0)` (componentName) en API < 33, por lo que el color sale 0xFF000000 | 1) Valor por defecto `false`, o recargar solo si hay icon pack y cambió su `versionCode`/`lastUpdateTime` (guardado en una pref). 2) Usar `data` o `getBlob(INDEX_ICON)`. 3) Usar `getInt(INDEX_COLOR)` en todas las versiones. **Las tres cosas en el mismo PR** | A/B/S | CONFIRMADO (código, verificador y logcat) |
| EVG-1b | P1 | La clave de estado de la caché se construye con campos perezosos | `LawnchairIconProvider.kt:205-207,229-235,407`. `LauncherAppState.java:168,303-307` | Calcular `iconPackVersion` e `isThemeEnabled` a partir de las prefs antes del primer `getSystemIconState` | A/B/S | HIPÓTESIS: solo con iconos temáticos. Medir con un log de `iconState` frente a `ICON_STATE` en 3 arranques |
| EVG-1c | P1 | `ACTION_TIME_TICK` refresca el modelo cada minuto por cada reloj del pack | `LawnchairIconProvider.kt:308-327`. Solo con icon pack (la pref por defecto es `""`). Lawnicons usado solo como icono temático no lo activa | Quitar TICK y dejar TIMEZONE, TIME_CHANGED y DATE_CHANGED; `ClockDrawableWrapper` ya se anima solo | A si hay pack / B / S | CONFIRMADO (condicionado) |
| EVG-1d | P2 | Doble sombra con `BlurMaskFilter` por software y copia ARGB en cada icono adaptativo | `BaseIconFactory.java:252-256` + `addPathShadow` (513-515) | Quitar `recreateIcon` en los adaptativos, o hacerlo solo en el modo modesto | M-A/M (aspecto)/S | CONFIRMADO |
| EVG-1e | P2 | El appfilter se parsea en cada proceso, el loader se bloquea y los mapas no son thread-safe | `IconPack.kt:27-44`, `LawnchairIconProvider.kt:56-59`, `CustomIconPack.kt:24-30,173`, `IconPackProvider.kt:20,31` | `ConcurrentHashMap` y `@Volatile`; serializar el mapa a disco con clave versionCode+lastUpdateTime; cargar `themedIconPack` solo si los iconos temáticos están activos | M/B/M | CONFIRMADO; el tiempo, HIPÓTESIS |
| EVG-1f | P2 | `SystemIconPack` se crea de nuevo en cada llamada (2 por icono con override), con `getActivityList` duplicado por perfil | `IconPackProvider.kt:23,41,46`, `SystemIconPack.kt:20-26,106-112` | Una sola instancia; `getActivityList(null, it)` | M/B/S | CONFIRMADO |
| EVG-1g | P3 | Drawables del pack a resolución completa | `CustomIconPack.kt:53` | `ImageDecoder.setTargetSize`, o ajustar la densidad | M/B/M | HIPÓTESIS (medir `allocationByteCount`) |
| EVG-1h | P3 | Tinte y temas en API 29: IPC y XML por icono | `LawnchairIconProvider.kt:170,186`, `ThemedIconCompat.kt:180-202`, `IconPackProvider.kt:93-96` | Caché por paquete y versión | M/B/M | CONFIRMADO (solo con tinte activado; por defecto, no) |

### EVG-E1: Arranque en frío

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-2 | **P0** | Room se abre y se hacen 3 `wal_checkpoint(full)` con `runBlocking` en el hilo principal en cada `onCreate` | `LawnchairLauncher.kt:254`, `data/AppDatabase.kt:28-38` | Hacerlo en `Dispatchers.IO` en `onStop` o antes de una copia de seguridad; con un checkpoint basta | A/B/S | CONFIRMADO |
| EVG-3 | P1 | Primera lectura en frío de 2 DataStores en el hilo principal (live-information se lee 2 veces en los inicializadores de propiedades, antes del `init`) | `PreferenceManager2.kt:224,504,741-742,786-787,804`, `MainThreadInitializedObject.java:44-63`, `SharedPreferencesMigration.kt:58-60` | Precalentar ambos DataStores en IO desde `LawnchairProcessInitializer`; valores remotos perezosos; flag persistido para la migración | A/M/M | CONFIRMADO; magnitud HIPÓTESIS (30-150 ms) |
| EVG-3b | **P0** | **Causa raíz real del borrado de la caché de iconos:** `restoreMissingPopupOptions` escribe `launcherPopupOrder` en cada `onCreate`. Su `onSet` llama a `reloadGrid()`, que lleva a `InvariantDeviceProfile.onConfigChanged`, que llama a `reloadIcons()` sin condición. El resultado es una recarga de la cuadrícula, un **borrado de la BD de iconos** y un reinicio del loader en cada arranque | `LauncherOptionsPopup.kt:31-41`, `PreferenceManager2.kt:311-315`, `InvariantDeviceProfile.java:556,583`. Confirmado en el dispositivo con la traza de `refreshAndReloadLauncher` y con la consulta a la BD (0 filas leídas, 101 en el fichero) | Escribir solo si `missingItems.isNotEmpty()` (**hecho**). Pendiente: que `onConfigChanged` solo recargue iconos si cambian `fillResIconDpi`/`iconBitmapSize` (EVG-3h) | A/B/S | **CONFIRMADO en el dispositivo, arreglado** |
| EVG-3h | P1 | `InvariantDeviceProfile.onConfigChanged` llama a `reloadIcons()` sin condición, añadido por Lawnchair (cualquier cambio de cuadrícula o de configuración borra la caché de iconos) | `InvariantDeviceProfile.java:583` | Recargar solo si cambian `iconBitmapSize` o `fillResIconDpi` | M/M/S | CONFIRMADO |
| EVG-3c | P2 | Smartspace consulta los widgets de GSA y abre un `AppWidgetHost` de forma anticipada | `SmartspaceProvider.kt:21-25`, `SmartspaceWidgetReader.kt:41-48`, `HeadlessWidgetsManager.kt:34-36` | Crear `widget` de forma perezosa, solo si `smartspaceAagWidget` y GSA lo justifican | M/B/S | CONFIRMADO |
| EVG-3d | P2 | El reportero de errores hace 3 IPC y E/S de disco antes de `Application.onCreate` | `LawnchairBugReporter.kt:23-54` | Dejar solo el `UncaughtExceptionHandler`; el resto a `UI_HELPER_EXECUTOR` | B/B/S | CONFIRMADO |
| EVG-3e | P3 | Fuentes Inter (unos 580 KB) parseadas en el hilo principal al arrancar el proceso | `FontCache.kt:71-74,350`, `MainProcessInitializer.java:47` | `Typeface` perezoso en IO | B-M/M/M | HIPÓTESIS |
| EVG-3f | P3 | Prioridad de carga del workspace visible | `FeatureFlags.java:124-127` (`ENABLE_WORKSPACE_LOADING_OPTIMIZATION` desactivado) | Probar a activarlo y medir el TTID | M/M/S | HIPÓTESIS |
| EVG-3g | P3 | `DeviceProfile`: de 17 a 25 lecturas por perfil y un `TextFactors` nuevo por llamada | `DeviceProfile.java:352,1160-1195`, `DeviceProfileOverrides.kt:58,92-135` | Instantánea inmutable de las prefs por cada IDP | M/M/M | CONFIRMADO |

### EVG-E9: Build y perfiles

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-4 | **P0** | ProfileInstaller no se ejecuta, así que el baseline profile del APK nunca llega a ART | `AndroidManifest-common.xml:188-191` elimina `InitializationProvider`; no hay llamadas a `ProfileInstaller` (el receiver sigue en el manifest fusionado). **El perfil sí se empaqueta**: el release contiene `assets/dexopt/baseline.prof` (12,8 KB) y `baseline.profm` (comprobado con `unzip -l`), así que el plugin lo recoge aunque esté en `src/lawnWithQuickstepRelease/` | Ejecutar `ProfileInstaller.writeProfile(context)` en segundo plano unos 5 s después del primer frame. Ampliar el generador: cajón, scroll, búsqueda. Añadir `nightly` al módulo | A/B/S | CONFIRMADO (que falta el instalador); refutado que el perfil no se empaquete |
| EVG-5 | P1 | `-dontoptimize` global en release | `proguard.pro:5` | Quitarlo; probar recientes, reflexión y hidden APIs | A/M/S | CONFIRMADO |
| EVG-5b | P1 | `-keep class com.android.** { *; }` anula el `allowshrinking/allowoptimization` de launcher3 | `proguard.pro:38` (también `:39 android.window.**`, `:56 android.view.**`); `proguard.flags:53,60` | Quitar `:38`; acotar el resto con `-whyareyoukeeping`/`-printusage` | A/M-A/M | CONFIRMADO; tamaño ganado, HIPÓTESIS |
| EVG-5c | P2 | `pseudoLocalesEnabled true` también en release | `build.gradle:242` (`buildTypes.all`) | Dejarlo solo en debug; opcionalmente `localeFilters` para builds personales | M/B/S | CONFIRMADO |
| EVG-5d | P3 | 4 ABIs empaquetadas | No hay `abiFilters` | `abiFilters "arm64-v8a", "armeabi-v7a"` | B/B/S | CONFIRMADO |
| EVG-5e | P3 | `google_fonts.json` (1,65 MB) se lee entero a un String | `GoogleFontsListing.kt:82` | JsonReader en streaming y bajo demanda | M/B/M | HIPÓTESIS (cuándo se invoca) |
| EVG-5f | P3 | `coreLibraryDesugaring` con minSdk 26 | `build.gradle:258-260,394` | Quitarlo si compila sin él | B/B/S | HIPÓTESIS |

### EVG-E2 / EVG-E4: Hilo principal, almacenamiento y fluidez

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-6a | **P0** | `firstBlocking` en cada frame o medición. `opto` = `runBlocking { get().first() }`, sin caché propia | Páginas: `Workspace.java:1468,1476-1481`; `PageIndicatorDots.java:170,445,454` vía `FeatureFlags.java:72-85` (`enableDotPagination=true`). Cajón: `ActivityAllAppsContainerView.java:166,807,834,843`. Iconos: `BubbleTextView.java:493` (la pref se evalúa antes de `mDisplay`), `:342`, `BaseAllAppsAdapter.java:247` | Campos leídos una vez: todas estas prefs hacen `recreate` en `onSet`. Invertir el orden del `&&` en `shouldUseTwoLine` | A/B/S | CONFIRMADO; coste por llamada, HIPÓTESIS |
| EVG-6b | P1 | Caché sistémica de preferencias | Más de 60 `firstBlocking` en el arranque y en las acciones; precedente en `LawnchairAppSearchAlgorithm.kt:42-54` | `PreferenceManager2.state()` con `stateIn(Eagerly)` + `value()` no bloqueante, precalentado en segundo plano; sustituir en `FeatureFlags` y en las rutas calientes | A/B-M/M | CONFIRMADO |
| EVG-7 | P1 | Room con `runBlocking` en cada pulsación larga | `WallpaperService.kt:98` (`getTopWallpapers`), `LawnchairLauncher.kt:349`, `WallpaperManagerCompat.kt:34` | `StateFlow` de "hay fondos", alimentado por un `Flow` de Room | M/B/S | CONFIRMADO |
| EVG-8 | P2 | Sheet opaco sobre el workspace y el hotseat en tablet, sin blur en API 29 | `AllAppsState.java:118-120,161-174,219-222`, `ActivityAllAppsContainerView.java:1490-1527` | En API < 31 en tablet: alfa de página 0, sin `HOTSEAT_ICONS` y escala 1 cuando el sheet está abierto; `drawRoundRect` o un path en caché | M/M/S-M | CONFIRMADO; ganancia, HIPÓTESIS (overdraw, gfxinfo) |
| EVG-8b | P2 | Carpetas del cajón: se inflan de nuevo en cada bind y los listeners se acumulan; `isContentSame` siempre es **false** para las carpetas, así que DiffUtil vuelve a enlazar siempre | `BaseAllAppsAdapter.java:171-172,358-360`, `FolderIcon.java:177-181,238`, `Folder.java:578,585` | Inflar una vez por ViewHolder, `Folder` perezoso, `removeListener` al reciclar, `isContentSame` correcto | A si hay carpetas / M / M | CONFIRMADO (solo con carpetas creadas por el usuario) |
| EVG-8c | P3 | Modo categorías: IPC por app y por pot en cada reconstrucción, en el hilo principal | `AppCategorizationUtils.kt:29`, `FlowerpotApps.kt:57-59`, `LawnchairAlphabeticalAppsList.kt:90,119` | Flags de `AppInfo`, caché por paquete, `MODEL_EXECUTOR`, `HashSet` | A si se usa / B / S-M | CONFIRMADO (desactivado por defecto) |
| EVG-8d | P3 | 3 instancias de `LawnchairAlphabeticalAppsList` (WORK y SEARCH procesan todo) | `ActivityAllAppsContainerView.java:291-296,670-671` | WORK y SEARCH con una lista simple o salida temprana | M (con categorías)/B/S | HIPÓTESIS |

### EVG-E5: Búsqueda

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-9 | **P0** | `combine()` retiene los resultados de apps hasta que responden la web, los archivos y los contactos (timeout de 1000 ms) | `LawnchairLocalSearchAlgorithm.kt:56-61,65,70-85`; `WebSuggestionProvider.kt:28-45` (sin `onStart{emit(empty)}`); valores por defecto en `PreferenceManager.kt:98` y `config.xml:169` | Emitir de inmediato apps, atajos y acciones, e ir combinando el resto (`onStart { emit(emptyList()) }` en cada proveedor) | A/B/S | CONFIRMADO |
| EVG-10 | P1 | Sin debounce; `cancel()` de AppSearch no hace nada; un `ModelUpdateTask` y una petición HTTP por pulsación | `AllAppsSearchBarController.java:103-110`, `LawnchairAppSearchAlgorithm.kt:27,68-72`, `LawnchairLocalSearchAlgorithm.kt:64,68-69,128-130` | Debounce de 150-300 ms para la web, número de secuencia o `collectLatest`, `@Volatile currentJob` | A/B/S | CONFIRMADO |
| EVG-10b | P1 | Unas 6 IPC a PackageManager sin caché por pulsación | `SearchTargetFactory.kt:221,533-545`, `ShortcutSearchProvider.kt:14,23-25`, `LawnchairUtils.kt:272` | Cachear el componente del market e `isDefaultLauncher`; invalidar con `PACKAGE_CHANGED` | M/B/S | CONFIRMADO |
| EVG-10c | P2 | El modo "solo apps" calcula en `Dispatchers.Main` y lee `AllAppsList.data` fuera del hilo del modelo | `LawnchairAppSearchAlgorithm.kt:58-63,89-103` | Calcular dentro de `execute()` y publicar solo el resultado | A en ese modo / B / S | CONFIRMADO (no es el modo por defecto) |
| EVG-10d | P2 | Iconos de resultados: `postAtFrontOfQueue` en el hilo del modelo, sin caché, con ids que incluyen la consulta | `SearchResultIcon.kt:68,152-154,206,215`, `SearchTargetFactory.kt:249` | `LruCache` por `(iconRes, tint)`, id estable y comprobar `boundId` | M/B/S-M | CONFIRMADO |
| EVG-10e | P2 | Unas 9 `firstBlocking` por pulsación y Regex por app | `AppSearchProvider.kt:17-20`, `WebSuggestionProvider.kt:32-34`, `AppMatcher.kt:55-56,82-84`, `AllAppsSearchInput.kt:309` | Preferencias en campos; Regex precompilado; tokens en caché | M/B/S | CONFIRMADO |
| EVG-10f | P2 | Animación de foco con `setPadding` en cada frame (300 ms, a la vez que el IME) | `AllAppsSearchInput.kt:276-290` | Animar `translationX` o `clipBounds`, o aplicar el padding sin animar | M/B/S | CONFIRMADO; coste, HIPÓTESIS |
| EVG-10g | P3 | Un `OkHttpClient` por proveedor y doble codificación de la consulta | `BuiltInWebSearchProviders.kt:37-41,67-68`, `CustomWebSearchProvider.kt:45` | Un cliente compartido y precalentado al enfocar | M/B/S | CONFIRMADO |
| EVG-10h | P3 | Archivos, contactos, ajustes, calculadora e historial (todos desactivados por defecto): sin `LIMIT`, `stat` por fila, reflexión y excepciones | `FileSearchProvider.kt:255,281,298-326`, `ContactsSearchProvider.kt:78-86`, `SettingsSearchProvider.kt:55-62`, `CalculatorSearchProvider.kt:43,60`, `HistorySearchProvider.kt:30` | `LIMIT` vía `sortOrder` en API < 30, cachés y prefiltros | A si se activa / B / S | CONFIRMADO |
| EVG-10i | P3 | Scopes de los algoritmos que no se cancelan; `SHA-256` compartido no thread-safe | `LawnchairAppSearchAlgorithm.kt:40`, `LawnchairLocalSearchAlgorithm.kt:49`, `SearchTargetFactory.kt:378-380` | `destroy()` que cancele; id sin hash o `ThreadLocal` | B/B/S | CONFIRMADO |

### EVG-E6: Animaciones

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-16 | P1 | NullPointerException creada y capturada en **cada apertura de app** (`mAppTransitionManager` es null sin recientes) | `QuickstepLauncher.java:286-290,1178`, `LawnchairLauncher.kt:406-411` | `if (!LawnchairApp.isRecentsEnabled) return getActivityLaunchOptionsDefault(v)` | B/B/S | CONFIRMADO |
| EVG-17 | P3 | Lecturas bloqueantes al abrir carpetas | `FolderAnimationManager.java:188,191`, `Folder.java:316` | Caché en `PreviewBackground`/`Folder` | B/B/S | CONFIRMADO |
| EVG-18 | P3 | `DepthController` crea animadores que no hacen nada en Q; `OnDrawListener` sin efecto en cada `onResume` | `DepthController.java:181`, `LawnchairLauncher.kt:451-467` | No crearlos en API < 30; quitar el listener | B/B/S | CONFIRMADO |
| EVG-19 | P3 | Fondo desenfocado (desactivado por defecto): 3-4 bitmaps a pantalla completa y GL en el hilo principal, más overdraw | `LauncherRootView.java:63-115` | 1/4 de resolución en RGB_565 en segundo plano; desactivado en el modo modesto | A si se activa / B / M | CONFIRMADO |

### EVG-E7 / EVG-E8: Memoria, segundo plano y batería

| ID | P | Título | Evidencia | Propuesta | I/R/E | Estado |
|---|---|---|---|---|---|---|
| EVG-12 | P1 | El host de widgets sin cabeza no deja de escuchar nunca; la barra de búsqueda del dock procesa actualizaciones y hace `measure` en segundo plano | `HeadlessWidgetsManager.kt:34-36,54-56`, `LawnQsbLayout.kt:156-169`, `SmartspaceProvider.kt:22`, `SmartspaceDataSource.kt:52-58` | `start/stopListening` en `onStart`/`onStop`; `repeatOnLifecycle(STARTED)`; cachear solo el `PendingIntent` | M-A/B/S-M | **CONFIRMADO en el dispositivo** (host 1028 con callbacks y la pantalla apagada) |
| EVG-13 | P1 | Smartspace (batería con `BATTERY_CHANGED`, NowPlaying con MediaController) recoge datos con la pantalla de inicio parada, porque `repeatOnAttached` solo se para al desacoplar la vista | `RepeatOnAttached.kt:14-33`, `BcSmartspaceView.kt:68-72,125`, `BatteryStatusProvider.kt:26,78`, `MediaListener.java:44-78,142` | Atar al `Lifecycle.STARTED` del launcher; `distinctUntilChanged`; filtrar por `EXTRA_MEDIA_SESSION` | M/B/S | CONFIRMADO |
| EVG-14 | P2 | `LauncherClient` se construye y se enlaza a GSA con `BIND_IMPORTANT` aunque el feed esté desactivado; `reconnect()` extra | `OverlayCallbackImpl.kt:39-45`, `LauncherClient.java:115-134,194-232`, `LawnchairLauncher.kt:97,167-170` | Overlay vacío si `!enableFeed`; cliente perezoso; `.drop(1)` | M/M/M | CONFIRMADO en el código; **en el dispositivo no se observó bind** (HIPÓTESIS) |
| EVG-15 | P1 | Scopes que no se cancelan y retienen la Activity anterior tras `recreate()` (modo oscuro, tema, más de 20 preferencias) | `GestureController.kt:39,80-86`, `SearchBarStateHandler.kt:22,27`, `LawnQsbLayout.kt:62,77` (además `setUpBackground` fuera del hilo principal), `SmartspacerView.kt:32,36` | `lifecycleScope` / `viewAttachedScope` | A/B/S | CONFIRMADO en el código; retención, HIPÓTESIS (`Activities` en `meminfo` tras 3 cambios de modo oscuro) |
| EVG-15b | P2 | Sin adaptación a poca RAM; `onTrimMemory` casi vacío; `RecentsModel` compara con `==` | grep de `isLowRamDevice` vacío; `Launcher.java:2251-2259`; `RecentsModel.java:261`; `BaseIconCache.java:149,520` | Con nivel ≥ `TRIM_MEMORY_BACKGROUND`, liberar las cachés y los packs que no se usan; base del modo modesto | M/B/M | CONFIRMADO |
| EVG-15c | P2 | Carrusel de fondos: el observer se acumula en cada pulsación larga y decodifica a resolución completa | `WallpaperCarouselView.kt:57,117,147`, `LawnchairUtils.kt:262`, `WallpaperViewModel.kt:35` | Observer ligado a la vista, `inSampleSize`/RGB_565, `onCleared` | A si se ejecuta / B / S | CONFIRMADO en el código; **probablemente no se ejecuta aquí** (sin fondos guardados ni permiso) |
| EVG-15d | P3 | `NotificationManager` guarda todas las notificaciones con sus extras | `NotificationManager.kt:20-26` | Guardar solo las multimedia | M/B/S | HIPÓTESIS (tamaño) |
| EVG-15e | P3 | Reloj de Smartspace a 1 Hz aunque solo muestre la fecha | `IcuDateTextView.kt:143-154`, `config.xml:145` | Sin tic si no se muestra la hora; si se muestra, alineado al minuto | B-M/B/S | CONFIRMADO |
| EVG-15f | P3 | `LauncherAppState` retiene el Launcher destruido | `LauncherAppState.java:86,257-258`, `Launcher.java:1849-1870` | `setLauncher(null)` en `onDestroy` | B/B/S | CONFIRMADO |
| EVG-15g | P3 | "Acerca de" consulta la API de GitHub de Lawnchair en cada apertura | `AboutViewModel.kt:43-44,70-72` | Quitarlo o cachearlo 24 h | B/B/S | CONFIRMADO |

### EVG-E10: Modo "dispositivo modesto"

Activo cuando `ActivityManager.isLowRamDevice()` o `SDK_INT < 31` (configurable en Ajustes, sección Rendimiento). Solo cambia **valores por defecto**: no toca lo que el usuario ya haya elegido.

| ID | P | Valor por defecto en el modo modesto | Base |
|---|---|---|---|
| EVG-20 | P1 | Infraestructura: flag, preferencia y sección en Ajustes | EVG-15b |
| EVG-21 | P2 | Sin la segunda sombra de los iconos (EVG-1d) ni la doble sombra de las etiquetas | `DoubleShadowBubbleTextView.java:62-75` |
| EVG-22 | P2 | Tablet en API < 31: workspace oculto bajo el sheet del cajón (EVG-8) | — |
| EVG-23 | P2 | Sugerencias web desactivadas (o con debounce mayor) | EVG-9 / EVG-10 |
| EVG-24 | P3 | Carrusel de fondos fuera del popup y fondo desenfocado bloqueado | EVG-15c / EVG-19 |
| EVG-25 | P3 | Menos vistas preinfladas en el cajón (`ALL_APPS_GONE_VISIBILITY`) | `AllAppsRecyclerViewPool.kt:126-131` |

### EVG-M: Ítems de medición (decidir midiendo, no suponiendo)

| ID | Qué | Cómo |
|---|---|---|
| EVG-M1 | Referencia de la tabla del apartado 5 con el APK release de Evergreen sin cambios | Script del apartado 5 |
| EVG-M2 | ¿Usas un icon pack o iconos temáticos? (condiciona EVG-1b, EVG-1c y EVG-1e) | Ajustes › Iconos en la tablet |
| EVG-M3 | Coste real de `firstBlocking` en el A53 | Microbenchmark de 10.000 llamadas en el dispositivo |
| EVG-M4 | ¿Se enlaza GSA al volver a la pantalla de inicio con la pantalla desbloqueada? | `dumpsys activity services com.google.android.googlequicksearchbox` en primer plano |
| EVG-M5 | ¿Hay fuga de la Activity tras un `recreate`? | Cambiar 3 veces el modo oscuro y mirar `meminfo` (`Activities:`) |

## 4. Dependencias

- **EVG-1:** sus tres partes van juntas, porque si solo se quita la recarga aparece C-1 y se sigue renderizando en silencio.
- **EVG-01 y EVG-02:** van antes que todo lo demás, porque sin ellos no hay métrica de aceptación.
- **EVG-4:** conviene volver a generar el perfil *después* de EVG-1, EVG-2 y EVG-6a, porque cambian las rutas calientes.
- **EVG-5 y EVG-5b:** cada uno en su PR y probándolo a fondo: arranque, cajón, búsqueda, widgets, ajustes y copia de seguridad.
- **EVG-6b:** sustituye a EVG-6a a largo plazo, pero EVG-6a es independiente y se puede entregar antes.
- **EVG-E10:** depende de EVG-20.

## 5. Plan de medición base (antes de tocar nada)

Siempre con el **release** (`assembleLawnWithQuickstepGithubRelease`, firmado con la clave de debug si no hay keystore) y con EVG-02 aplicado. Ejecuta los comandos con `adb -s HA12S9CD` (también hay un Pixel conectado).

```bash
PKG=io.github.jtorregrosa.evergreen
ACT=$PKG/app.lawnchair.LawnchairLauncher
# Evergreen como launcher por defecto (o lanzarlo por componente); estados de compilación:
adb shell cmd package compile -m verify -f $PKG         # recién instalado y sin perfil
adb shell cmd package compile -m speed-profile -f $PKG  # con perfil
# Arranque en frío (10 repeticiones; quedarse con la mediana; ignorar TotalTime=0):
for i in $(seq 10); do adb shell am force-stop $PKG; adb shell am start -W -n $ACT | grep TotalTime; sleep 8; done
adb logcat -d | grep -E "Displayed $PKG|Fully drawn $PKG"
adb logcat -d | grep -c "using fallback bulk icon loading"   # debe ser 0 tras EVG-1
# Fluidez del cajón y de las páginas:
adb shell dumpsys gfxinfo $PKG reset; (abrir el cajón, 10× `adb shell input swipe 600 1500 600 300 150`); adb shell dumpsys gfxinfo $PKG
# Perfetto en Android 10:
adb shell setprop persist.traced.enable 1
# record_android_trace -o trace.perfetto -t 15s -a $PKG sched freq idle am wm gfx view binder_driver dalvik disk
# Memoria y muertes:
adb shell dumpsys meminfo $PKG; adb logcat -b events | grep -E "am_proc_died|am_kill"
# Overdraw:
adb shell setprop debug.hwui.overdraw show
```

**Tabla de referencia:** Lenovo TB-X606F, APK release y 8 arranques en frío por celda, con `am start -W -n` (Lawnchair sigue como launcher por defecto y la pantalla, encendida y desbloqueada). Se muestra la mediana con el rango entre paréntesis.

| Métrica | Lawnchair 15b3 de serie | Evergreen base (`20a7ccd`) | + EVG-1/EVG-2 (`d38d7bb`) | + EVG-3b (`acbb5fd`) |
|---|---|---|---|---|
| TotalTime en `verify` (sin AOT) | — | **2287 ms** (2165–2606) | 2216 ms (2144–2323) | **1872 ms** (1819–1922), **−18 %** |
| TotalTime en `speed` (AOT completo) | ≈ 2,32 s (`speed-profile`) | **1700 ms** (1649–2168) | 1656 ms (1639–1667) | **1421 ms** (1396–1436), **−16 %** |
| TTFD (`Fully drawn`) | — | igual a TotalTime | igual a TotalTime | igual a TotalTime |
| Fallbacks de iconos por arranque | 15–30 | 14 | 14 | **0** |
| PSS al terminar la tanda (`speed`) | ≈ 187 MB | 204 MB | 211 MB | 111 MB (dato orientativo, de una sola muestra) |
| Fotogramas lentos (jank) en el scroll del cajón | — | | | |
| Desde la tecla hasta los resultados de apps | — | | | |

EVG-1 y EVG-2 apenas mueven el arranque: el borrado real lo provocaba EVG-3b, que tapaba el arreglo de las columnas. Con EVG-3b la caché de iconos por fin se lee desde la BD.

## 6. Descartados o corregidos

| Hallazgo | Motivo |
|---|---|
| "La animación suck-in con capa por software es la de cierre por defecto" (audit inicial n.º 8) | **No se ejecuta en esta tablet**: hace falta un `GestureNavContract`, que solo envía el proveedor de recientes en R+ al deslizar hacia arriba. Aquí son recientes de Lenovo en Q con navegación de 3 botones. El arreglo queda como mejora menor dentro de E10 |
| "C-1 causa los fallbacks de logcat" | El bug es real, pero el log lo produce el borrado de EVG-1 (la BD está vacía antes del loader). C-1 hace que el renderizado vuelva a ocurrir en silencio |
| "`isContentSame` siempre devuelve true para las carpetas" | Es al revés: siempre **false** (`itemInfo` nunca es null). Ya está recogido en EVG-8b |
| "Falta un `break` en `VIEW_TYPE_PRIVATE_SPACE_HEADER`" | Sí lo tiene (`BaseAllAppsAdapter.java:341`) |
| "`CellLayout.isOccupied` en los bucles de reordenación" | La reordenación usa `mOccupied.cells`; `isOccupied` solo se usa al soltar y en accesibilidad. Las llamadas calientes reales son `ReorderAlgorithm.java:135` e `isRegionVacant` (impacto bajo) |
| "Un `contains` O(N·M) en flowerpot" | `pot.rules` es un Set; el `contains` lineal está en `LawnchairAlphabeticalAppsList.kt:119` y solo aplica con carpetas |
| "`getHeaderColor` parsea JSON" | `ColorOption.fromString` es un `when` + `parseColor` |
| "`baseline-profile` apunta a `app.lawnchair`" | Ya se corrigió en el renombrado |
| "El baseline profile no se empaqueta porque está en un source set que no usa ninguna variante" (I-3) | El APK release contiene `assets/dexopt/baseline.prof` y `.profm`. Lo que falta es solo instalarlo (EVG-4) |
| "C-1 solo afecta a API < 33" | Tras el commit `cc37c52` del submódulo, `getBlob(2)` se ejecuta en **todas** las versiones. Corregido en EVG-1 |
| `Workspace.onInterceptTouchEvent`, `PagedView`, `shouldTextBeVisible` | Frecuencia baja (ACTION_DOWN o el final del gesto), no por frame |
| `material-icons-extended` | R8 ya los elimina; impacto en tiempo de ejecución despreciable |
| `DepthController` / blur | En Q no hacen nada (solo queda el residuo de EVG-18) |

## 7. Riesgos y qué no tocar

- **Divergencia con AOSP:** conviene parchear de forma localizada en `src/` y `quickstep/` (por ejemplo, EVG-6a y EVG-16) y preferir los cambios en `lawnchair/src`, para poder seguir trayendo arreglos de la rama 15 de Lawnchair (`git fetch upstream 15-dev`).
- **R8 (EVG-5 y EVG-5b):** hay reflexión sobre clases de SystemUI y wm.shell, APIs ocultas (RestrictionBypass) y AIDL. Hace falta probar la ruta de recientes, aunque en esta tablet no se use, y los widgets.
- **Cambios visibles:**
  - EVG-1d (sombra de los iconos), EVG-8 (cómo se ve el cajón en tablet) y EVG-21: siempre detrás del modo modesto.
  - EVG-1: valor por defecto nuevo, sin impacto visible.
- **Datos del usuario:** ningún cambio debe migrar ni borrar preferencias. Los valores por defecto nuevos solo se aplican cuando el usuario no ha elegido nada.
