# IBM Z Datathon 2026 — final submission checklist

This checklist separates repository checks already passed from checks that must be performed on the actual event VM. A green CI run does not prove that the separate virtual server has been installed or is reachable.

## Verified on main (18 October 2026)

- [x] Latest submission-polish commit: [a99cc2535c5788a25b40e6a0d838b0995c1bd4e4](https://github.com/PantheonDeified/FloodWatch-South-India/commit/a99cc2535c5788a25b40e6a0d838b0995c1bd4e4).
- [x] GitHub Pages build/deployment passed: [run #39131306933](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131306933).
- [x] Frontend JavaScript and calculated-risk regression passed: [run #39131307073](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307073).
- [x] Backend tests, container build and installer shell syntax passed: [run #39131307093](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307093).
- [x] Deployed-site and public water-snapshot smoke checks passed: [run #39131307064](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307064).
- [x] The demo guide and installer are in the repository: [IBM Z Datathon demo guide](IBM_Z_DATATHON_DEMO.md) · [LinuxONE VM runbook](../deploy/ibm-linuxone/README.md).

## Required on the actual Ubuntu VM

- [ ] Run `uname -m` and `lscpu`; record the output. Do not infer the processor architecture from the VM label.
- [ ] From a clone of the repository, run `bash deploy/ibm-linuxone/install-user-service.sh`.
- [ ] Capture successful `systemctl --user status floodwatch-api`, `/health`, `/api/v1/status`, and `/api/v1/models/status` output.
- [ ] Run `bash deploy/ibm-linuxone/run-regional-lstm.sh preflight`; on LinuxONE, save the exact compatibility result. Do not claim LSTM training on the VM unless `preflight` succeeds and `train` completes there.
- [ ] If connecting the public webpage to the API, use HTTPS, verify the configured CORS origin and never expose port 8000 directly to the public Internet.
- [ ] Open the site in a clean browser and check: location search, continuous contours, one cell popup, one station timestamp, NASA overlay and source-check status.
- [ ] Confirm the current submission portal, registered team details, eligibility, and rules about pre-existing project code with the organiser if not already confirmed.
- [ ] Upload the public repository URL, pitch deck and demo video in the organiser's requested format. Keep the video within the event's actual limit.

## Model metrics — state accurately

The five-state regional discharge LSTM evaluation used 89,824 chronological held-out targets. Raw LSTM test RMSE was **830.45 m³/s**, persistence baseline RMSE was **700.88 m³/s**, and a validation-selected **25% LSTM / 75% persistence blend** achieved test RMSE **649.63 m³/s** (7.3% lower pooled RMSE than persistence). Raw LSTM alone underperformed; station-level and high-flow performance was mixed.

The model predicts discharge, not flood probability, inundation depth or evacuation routes. It is not served by the current API or wired into the map's score. The risk contours are a separate provisional index, not calibrated flood probabilities or official alerts.

## Important security rule

Never commit cloud passwords, SSH private keys, API tokens, tunnel credentials or account identifiers to the public repository or slides. The installer does not need these values.
