# FloodWatch South India

An interactive, browser-based weather and flood situational-awareness prototype for South India, inspired by public flood-monitoring dashboards.

## Run it

This first frontend version is a static website: open [index.html](./index.html) in a modern browser, or publish it with GitHub Pages (steps below). An internet connection is required for the map and public-data APIs.

## Publish with GitHub Pages

1. Open the repository's **Settings** tab.
2. Select **Pages** in the left sidebar.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select branch **main** and folder **/ (root)**, then press **Save**.
5. Wait a minute or two and refresh the Pages screen. GitHub will show the public website URL.

The page should be available at `https://pantheondeified.github.io/FloodWatch-South-India/` after GitHub Pages finishes publishing. If that URL does not open, check the Pages status and repository visibility/settings.

## Features

- Interactive South India map with street, terrain and satellite basemaps.
- Search for towns, villages, districts and landmarks; browser geolocation is optional and only used after you press **My location** and approve the browser prompt.
- Location-specific current weather and hourly rain-probability forecast from the Open-Meteo public API.
- Public tropical-cyclone event feed attempt via GDACS.
- Responsive layout for desktop and mobile.

## Data and limitations

- Weather values are model estimates, not direct measurements at every coordinate.
- OpenStreetMap, OpenTopoMap and Esri map tiles have their own availability and usage terms.
- Public geocoding and event APIs can be rate-limited, unavailable, or changed by their providers.
- This prototype does **not** currently provide official flood warnings, verified river-gauge feeds, or an operational hydrological flood forecast. Buttons and data availability can vary as public sources change.
- This is an independent project and is **not affiliated with or endorsed by Google Flood Hub**. It must not be used as the sole basis for emergency decisions. Follow official IMD and state disaster-management guidance.

## License

The project is distributed under the MIT License. External map tiles and data providers remain subject to their own terms and attribution requirements.
