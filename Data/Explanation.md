# Data used in our electricity-prediction project

Our source is the **ADRENALIN** dataset on [Zenodo, DOI 10.5281/zenodo.15012288](https://doi.org/10.5281/zenodo.15012288). The local [dataset description](../ADRENALIN_data_description.pdf), preparation scripts and saved processing reports document the conventions below. Retained raw meter and weather values are preserved; processing writes separate derived files. The historical filename filter deletes unmatched CSV files, so it must only be used on an authorised working copy.

## Locations, buildings and experiment roles

`Data/BuildingsByLocation/` contains locations **L03, L07 and L14**. The primary validation-guided experiment uses these roles:

| Building | Selected electricity channel | Role |
| --- | --- | --- |
| L03_B01 | EM02.Pt | Development: chronological fitting/validation, then full-development refit |
| L07_B01 | EM01.Pt | Held-out test: unseen location |
| L14_B01 | EM01.Pt | Held-out test: unseen building at a location represented in development |
| L14_B02 | EM01.Pt | Held-out test: unseen building at a location represented in development |
| L14_B03 | EM02.Pt | Held-out test: unseen building at a location represented in development |
| L14_B04 | EM02.Pt | Development: chronological fitting/validation, then full-development refit |
| L14_B05 | EM02.Pt | Development: chronological fitting/validation, then full-development refit |

Within each development building, the earliest `floor(0.8 × number of unique interval-start timestamps)` fit the methods; the remaining timestamps validate them. All rows at the same timestamp remain together. Cutoffs differ by building. These are future periods of known buildings, rather than unseen-building validation. After selecting shared model settings, all development rows are used for refitting. The test buildings were already inspected in earlier experiments. A separate exploratory sensitivity excludes L03 from development; it does not change the primary split above.

## Layout and file naming

- `Lxx/Lxx_Byy/1h/adrenalin.1h.Lxx.Byy.EMzz.Pt.csv`: retained raw electricity readings; `1h` identifies the sampling frequency. Counter semantics are confirmed separately, rather than inferred from the filename.
- `Lxx/Lxx_Byy/Lxx_Byy-building_info.txt`: metadata such as gross floor area, use, climate zone and heating/cooling equipment. The corresponding `-topology.txt` describes meter relationships. Selected channels are assigned to building tables; complete whole-building meter coverage is not independently established for every channel.
- `Lxx/Lxx_WS/adrenalin.1h.Lxx.WS01.<quantity>.csv`: location weather series shared by buildings at that location.
- `L07/L07_B01/processed/`: accepted counter differences (`.hourly_energy.csv`), excluded intervals (`.excluded_intervals.csv`) and conversion provenance (`.processing_report.txt`).
- `Lxx/unifieddataconsumption/<building>_consumption.csv`: electricity with building identity and interval start/end.
- `Lxx/unifieddataconsumption/<building>_consumption_weather.csv`: the consumption table with six weather fields.

The enrichment/export scripts are configured to generate `<building>_model_input.csv` and `<building>_targets.csv` alongside those unified tables. The active, already-staged modelling copies instead live in `Prediction Model/Input Data/` and `Prediction Model/Target Set/`. Upstream regeneration does **not** refresh staged copies automatically; targets must retain their matching input row order.

## Units and target

Electricity values retain their stated **kWh** units. The target for each hourly interval is:

```text
electricity_kwh_per_m2 = electricity_kwh / floor_area_m2
```

`floor_area_m2` is gross total floor area in **square metres (m²)**. The resulting target is **kWh/m² for that hourly interval**, not an annual total. Decimal arithmetic uses 28 significant digits during generation. Missing or ambiguous metadata stays empty; explicit YES/NO becomes 1/0. Heating/cooling heat pumps are distinguished from tap-water equipment. No arbitrary category codes are assigned during enrichment.

L03 retains its stated unit and values. Its unusually large consumption-per-area scale is unresolved; no L03-specific divide-by-1,000 correction is established or applied. The selected L03 channel is EM02, not the separate EM01 virtual aggregate.

## L07 counter conversion

[`cumulative_channels.json`](../Data_cleaning/cumulative_channels.json) explicitly confirms L07_B01 EM01.Pt as cumulative. Adjacent original readings are differenced only for accepted one-hour intervals. Negative changes, their immediately following original intervals, invalid readings, gaps and duplicate/invalid timestamps are handled conservatively; missing periods are not interpolated or bridged. Raw counters remain intact.

The saved L07 report records **9,545 counter readings**, **9,543 accepted hourly intervals** and **one excluded two-hour interval** (1 December 2021, 20:00–22:00 UTC). The first reading supplies the initial counter reference. The saved exclusion is a gap, not evidence that resets occurred in this run. The configuration also retains historical L06 entries, although no L06 data directory is present in our current seven-building selection.

## Timestamp and weather assumptions

- **L03/L14 interval convention:** source timestamps are treated as interval ends; starts are one hour earlier. This is a project assumption, not a verified dataset-wide labelling guarantee. Their readings are used directly without counter differencing or rescaling.
- **L07 bounds:** processed counter differences retain their original start/end bounds.
- **Prediction interval:** the intended forecast at time `t` concerns electricity over `[t, t + 1 hour)`. Targets already match their interval rows and are not shifted again.
- **Time zone:** tables and calendar features use UTC. No documented local time-zone mapping is available in the project.
- **Weather join:** `join_weather_data.py` left-joins weather by exact `interval_start_utc` equality, after checking units and weather timestamp uniqueness. Electricity row order/values remain intact; unmatched weather remains missing.
- **Availability assumption:** exact-t historical/reanalysis weather is treated as available at prediction time, but publication latency and selected-variable interval semantics are not established. The separate one-hour-lag sensitivity does not establish operational availability either.

| Source quantity | Model-input field | Unit |
| --- | --- | --- |
| T | temperature_c | °C |
| Rh | relative_humidity_pct | % |
| Ws | wind_speed_kmh | km/h |
| Wd | wind_direction_deg | degrees |
| Rd | direct_solar_radiation_wm2 | W/m² |
| Rr | diffuse_solar_radiation_wm2 | W/m² |

Evidence is retained in [the energy inspection report](../Data_cleaning/energy_readings_report.txt), [the metadata report](../Data_cleaning/building_metadata_report.txt), the L07 processing report and [our progress report](../progress_so_far.md). Saved provenance contains original-machine absolute paths; those records are preserved as-is. This explanation does not alter datasets or numerical results.
