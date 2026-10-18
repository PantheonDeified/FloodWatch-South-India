# IBM Z Datathon 2026 — final submission checklist

This checklist separates repository checks already passed from checks that must be performed on the actual event VM. A green CI run does not prove that the separate virtual server has been installed or is reachable.

## Verified on main (18 October 2026)

- [x] Current main includes the datathon demo guide, LinuxONE deployment runbook and model runner. Re-check the linked CI workflows for the exact submission commit before final upload.
- [x] GitHub Pages build/deployment passed: [run #39131306933](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131306933).
- [x] Frontend JavaScript and calculated-risk regression passed: [run #39131307073](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307073).
- [x] Backend tests, container build and installer shell syntax passed: [run #39131307093](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307093).
- [x] Deployed-site and public water-snapshot smoke checks passed: [run #39131307064](https://github.com/PantheonDeified/FloodWatch-South-India/actions/runs/39131307064).
- [x] The demo guide and installer are in the repository: [IBM Z Datathon demo guide](IBM_Z_DATATHON_DEMO.md) · [LinuxONE VM runbook](../deploy/ibm-linuxone/README.md).

## Required on the actual Ubuntu VM

- [ ] Connect using the local `FloodWatchKey.pem` file as documented in the [LinuxONE runbook](../deploy/ibm-linuxone/README.md). Do not upload the key.
- [ ] Run `uname -m` and `lscpu`; record the output. Do not infer the processor architecture from the VM label.
- [ ] From a clone of the repository, run `bash deploy/ibm-linuxone/install-user-service.sh`.
- [ ] Capture successful `systemctl --user status floodwatch-api`, `/health`, `/api/v1/status`, and `/api/v1/models/status` output.
- [ ] After training, call `/api/v1/models/regional-discharge/forecast`, verify seven forecast rows and the source-history end date, and check that no server filesystem paths are returned.
- [ ] Run `bash deploy/ibm-linuxone/run-regional-lstm.sh setup`, then `preflight`, then `train`; save successful command output and the installed PyTorch version. The official CPU index lists `torch 2.10.0+cpu` wheels for CPython 3.12 `linux_s390x`, but your VM run still must pass.
- [ ] If connecting the public webpage to the API, use HTTPS, verify the configured CORS origin and never expose port 8000 directly to the public Internet.
- [ ] Open the site in a clean browser and check: location search, continuous contours, one cell popup, one station timestamp, NASA overlay and source-check status.
- [ ] Confirm the current submission portal, registered team details, eligibility, and rules about pre-existing project code with the organiser if not already confirmed.
- [ ] Upload the public repository URL, pitch deck and demo video in the organiser's requested format. Keep the video within the event's actual limit.

## Model metrics — state accurately

The five-state regional discharge LSTM evaluation used 89,824 chronological held-out targets. Raw LSTM test RMSE was **830.45 m³/s**, persistence baseline RMSE was **700.88 m³/s**, and a validation-selected **25% LSTM / 75% persistence blend** achieved test RMSE **649.63 m³/s** (7.3% lower pooled RMSE than persistence). Raw LSTM alone underperformed; station-level and high-flow performance was mixed.

The new API route can run the saved-weight regional predictor when the VM has local model assets. It predicts discharge, not flood probability, water level, inundation depth or evacuation routes, and it is not wired into the map's score. The risk contours are a separate provisional index, not calibrated flood probabilities or official alerts.

## Important security rule

Never commit cloud passwords, SSH private keys, API tokens, tunnel credentials or account identifiers to the public repository or slides. The installer does not need these values.
