# Evergreen brand

<p>
  <img src="png/evergreen-lockup-on-light.png#gh-light-mode-only" alt="Evergreen" width="360">
  <img src="png/evergreen-lockup-on-dark.png#gh-dark-mode-only" alt="Evergreen" width="360">
</p>

The Evergreen mark is a two-tone fir tree with a house in it, because a launcher is the home screen. The left half is lit and the right half is in shade. Curved bands mark each tier of the tree.

All assets in this folder, the app's adaptive icon and the store icons come from one geometry definition in [`generate.py`](generate.py). If you change the logo, change the script and run it again. Don't edit the outputs by hand.

```bash
python docs/branding/generate.py
```

Rasterising needs Chrome or Edge. If the script can't find the browser, set `CHROME` to its path.

## Logo

| File | Use |
| --- | --- |
| [`evergreen-logo.svg`](evergreen-logo.svg) | Master logo, full colour, transparent background, 512 grid |
| [`evergreen-logo-mono.svg`](evergreen-logo-mono.svg) | Single colour. The house is cut out of the tree. Use it for stamps, watermarks and themed icons |
| [`evergreen-icon.svg`](evergreen-icon.svg) | App icon as a launcher shows it: the logo on the dark background in a rounded square |
| [`png/evergreen-logo-1024.png`](png/evergreen-logo-1024.png) | Raster master, transparent |
| [`png/evergreen-icon-512.png`](png/evergreen-icon-512.png) | Full-bleed square icon for Google Play and F-Droid (the store applies its own mask) |
| [`png/evergreen-icon-rounded-512.png`](png/evergreen-icon-rounded-512.png) | Rounded icon for READMEs, websites and social media |
| [`png/evergreen-lockup-on-dark.png`](png/evergreen-lockup-on-dark.png), [`png/evergreen-lockup-on-light.png`](png/evergreen-lockup-on-light.png) | Logo and wordmark |
| [`png/evergreen-feature-graphic.png`](png/evergreen-feature-graphic.png) | 1024 × 500 store feature graphic |

### Construction

- 512 × 512 grid, with the seam between the two halves at x = 256.
- Every tier edge has the same slope (0.75), and every notch is 40 px deep.
- Outer corners have an 8 px radius. A 4 px light rim runs along the inside of the outline.
- The three band curves are one shape at different scales. Each one runs from the seam to a tier tip, and the lowest one starts at the top of the roof.
- The house and the door are centred on the seam, and the door's two colours split along it.
- Leave clear space of at least one notch depth (40 px on the 512 grid) around the logo. Don't put the logo on a mid-green background, because the tree disappears into it.

## Colour

| Role | Left (lit) | Right (shade) |
| --- | --- | --- |
| Top tier | `#BDEF9E` → `#A3E588` | `#62BF8D` → `#4FAB82` |
| Second band | `#94E07C` → `#78D274` | `#43A07C` → `#358870` |
| Third band | `#62C86E` → `#46BA6C` | `#2F7C68` → `#25685F` |
| Base | `#34B06B` → `#27A265` | `#1E5A5B` → `#1A4D53` |
| Door | `#3CB46C` | `#1A4D53` |

| Neutral | Value |
| --- | --- |
| Icon background | `#2E3A38` → `#1A2522` |
| Ink on light backgrounds | `#1F3D33` |
| Ink on dark backgrounds | `#E9F5EC` |
| House | `#FFFFFF` |

## Type

The wordmark is set in [Outfit](https://fonts.google.com/specimen/Outfit) SemiBold (600) with −1% tracking, and the supporting text in Outfit Medium (500). Outfit is licensed under the SIL Open Font License 1.1. The rounded geometric letters match the logo's rounded corners.

## Android

| Resource | What it is |
| --- | --- |
| `lawnchair/res/drawable/ic_evergreen_foreground.xml` | Adaptive icon foreground: points to the anti-aliased PNG layers in `res/mipmap-*` (`ic_launcher_home_foreground.png`). The logo is centred in the 108 dp canvas at about 60% of the 72 dp visible area, so round masks leave a margin. A vector foreground would need `<clip-path>`, which Android does not anti-alias |
| `lawnchair/res/drawable/ic_evergreen_background.xml` | Adaptive icon background: dark gradient |
| `lawnchair/res/drawable/ic_launcher_home_monochrome.xml` | Themed icon layer (Android 13 and later): the mono logo |
| `res/mipmap-*/ic_launcher_home*.png` | Legacy raster icons, kept in sync with the adaptive icon |
| `fastlane/metadata/android/en-US/images/icon.png`, `featureGraphic.png` | Store listing images |
