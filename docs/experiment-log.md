# Experiment log

93 configurations, measured against 300 emails labelled by hand. Tuning used one half
of them. The TEST column is the other half, which the tuning never saw.

## topic

| configuration | train | test | baseline | lift |
|---|---|---|---|---|
| M1 narrow admin | 57% | 67% | 34% | +33% |
| L work=colleague mkt=bulk adm=base | 59% | 67% | 34% | +33% |
| M2 admin dropped | 57% | 67% | 34% | +33% |
| L work=colleague mkt=sell adm=base | 59% | 66% | 34% | +32% |
| K6 work colleague | 60% | 65% | 34% | +31% |
| L work=colleague mkt=base adm=base | 60% | 65% | 34% | +31% |
| M6 six classes | 58% | 65% | 34% | +31% |
| M4 money paid | 57% | 64% | 34% | +30% |
| M5 family personal | 61% | 63% | 34% | +29% |
| K8 marketing sell | 58% | 62% | 34% | +28% |
| K9 marketing bulk | 54% | 62% | 34% | +28% |
| L work=base mkt=sell adm=base | 58% | 62% | 34% | +28% |
| L work=base mkt=bulk adm=base | 54% | 62% | 34% | +28% |
| L work=colleague mkt=sell adm=personal | 59% | 62% | 34% | +28% |
| L work=colleague mkt=bulk adm=personal | 59% | 62% | 34% | +28% |
| M3 money bill | 59% | 62% | 34% | +28% |
| L work=colleague mkt=base adm=personal | 57% | 61% | 34% | +27% |
| N4 body length chosen per question | 54% | 61% | 34% | +27% |
| D1 raw argmax | 58% | 61% | 34% | +27% |
| E1 is about raw argmax | 58% | 61% | 34% | +27% |
| E5 average of four phrasings | 57% | 61% | 34% | +27% |
| H0 no weights | 58% | 61% | 34% | +27% |
| H1 learned weights seed 3 | 69% | 61% | 34% | +27% |
| I7 keep quoted text | 58% | 61% | 34% | +27% |
| J2 footer removed | 58% | 61% | 34% | +27% |
| J3 footer kept | 58% | 61% | 34% | +27% |
| J5 sender name only | 61% | 61% | 34% | +27% |
| K2 admin personal | 58% | 61% | 34% | +27% |
| L work=base mkt=base adm=personal | 58% | 61% | 34% | +27% |
| L work=base mkt=sell adm=personal | 59% | 61% | 34% | +27% |
| H1 learned weights seed 1 | 70% | 60% | 34% | +26% |
| K10 marketing offer | 59% | 60% | 34% | +26% |
| I5 no sender | 61% | 59% | 34% | +25% |
| J4 subject first, no keys | 58% | 59% | 34% | +25% |
| K1 admin narrow | 58% | 59% | 34% | +25% |
| N2 sender and content averaged | 60% | 59% | 34% | +25% |
| J6 domain and subject | 57% | 59% | 34% | +25% |
| E6 average of three phrasings | 53% | 58% | 34% | +24% |
| I6 with recipients | 57% | 58% | 34% | +24% |
| K3 admin account | 55% | 58% | 34% | +24% |
| K4 admin verify | 51% | 58% | 34% | +24% |
| H1 learned weights seed 2 | 69% | 57% | 34% | +23% |
| K7 work business | 51% | 57% | 34% | +23% |
| N3 sender or content, whichever is higher | 56% | 57% | 34% | +23% |
| I3 body 800 | 55% | 57% | 34% | +23% |
| L work=base mkt=bulk adm=personal | 55% | 57% | 34% | +23% |
| I4 body 1500 | 53% | 56% | 34% | +22% |
| I8 explicit OTHER question | 53% | 56% | 34% | +22% |
| I2 body 350 | 55% | 54% | 34% | +20% |
| J1 subject twice | 53% | 54% | 34% | +20% |
| K5 work project | 53% | 53% | 34% | +19% |
| D3 zscore argmax | 50% | 53% | 34% | +19% |
| I1 body 200 | 53% | 52% | 34% | +18% |
| D2 percentile argmax | 46% | 51% | 34% | +17% |
| D4 percentile, OTHER under 0.3 | 46% | 51% | 34% | +17% |
| D5 mix binary 0.75 + choice | 51% | 51% | 34% | +17% |
| C1 plain | 45% | 50% | 34% | +16% |
| D4 percentile, OTHER under 0.5 | 45% | 50% | 34% | +16% |
| D4 percentile, OTHER under 0.7 | 45% | 50% | 34% | +16% |
| D5 mix binary 0.50 + choice | 53% | 49% | 34% | +15% |
| E2 filed under raw argmax | 47% | 49% | 34% | +15% |
| D5 mix binary 0.25 + choice | 53% | 49% | 34% | +15% |
| B6 body 1000 | 55% | 47% | 34% | +13% |
| B5 body 500 | 56% | 47% | 34% | +13% |
| B4 body 300 | 56% | 46% | 34% | +12% |
| A3 from+subject+body200 | 52% | 45% | 34% | +11% |
| A7 no quoted reply | 52% | 45% | 34% | +11% |
| B3 body 200 | 52% | 45% | 34% | +11% |
| B9 keyword options | 56% | 45% | 34% | +11% |
| B10 subject-led question | 53% | 45% | 34% | +11% |
| C2 keywords | 44% | 45% | 34% | +11% |
| D4 percentile, OTHER under 0.8 | 41% | 45% | 34% | +11% |
| A5 sender domain only | 48% | 45% | 34% | +11% |
| A8 clean both | 51% | 44% | 34% | +10% |
| B12 topic word | 55% | 44% | 34% | +10% |
| A6 no urls | 51% | 43% | 34% | +9% |
| B8 one word options | 53% | 43% | 34% | +9% |
| B11 filing question | 51% | 43% | 34% | +9% |
| A2 subject+body200 | 49% | 41% | 34% | +7% |
| B2 body 150 | 52% | 41% | 34% | +7% |
| A4 plain string | 40% | 40% | 34% | +6% |
| E3 sender type raw argmax | 37% | 40% | 34% | +6% |
| B1 body 80 | 51% | 38% | 34% | +4% |
| D4 percentile, OTHER under 0.9 | 27% | 37% | 34% | +3% |
| B7 longer options | 39% | 37% | 34% | +3% |
| A1 subject only | 37% | 35% | 34% | +1% |
| N1 sender questions | 43% | 34% | 34% | +0% |
| E4 one word raw argmax | 46% | 33% | 34% | -1% |

## action

| configuration | train | test | baseline | lift |
|---|---|---|---|---|
| G1 cascade, tuned thresholds | 59% | 65% | 63% | +3% |
| G2 always answer READ | 56% | 63% | 63% | +0% |
| F1 plain raw argmax | 45% | 49% | 63% | -13% |
| F3 evidence raw argmax | 35% | 39% | 63% | -24% |
| F2 direct raw argmax | 7% | 21% | 63% | -42% |

