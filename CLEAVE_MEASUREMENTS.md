# Cleave edge measurements

Engineering / Vision shows left and right cleave measurements in both camera
views. Blue is an ideal line perpendicular to that fiber's fitted centerline;
white is the fitted edge. Both pass through the sampled edge's center.

- Angle error: signed deviation from perpendicular, in degrees. Zero is ideal.
- RMS: root mean square perpendicular distance of edge samples from the fitted line.
- Max: largest absolute perpendicular distance of an observed sample from that line.

A tilted but straight cleave has angle error and near-zero RMS. A rough edge
has nonzero RMS/max. Max is an observed edge deviation, not a confirmed chip size.
No Pearson correlation is reported because the ideal constant axial position
has zero variance. No arbitrary pass/fail threshold is applied.

Lengths use the existing per-camera scale when calibrated, otherwise pixels.
The existing tracer samples up to 29 positions across the central 84% of the
cladding height. At least eight resolved raster rows and half-diameter coverage
are required. All accepted samples are retained so defects are not filtered out
of the fit. Unresolved, invalid, or stale images do not display numeric scores.
These are 2D silhouette estimates: focus, thresholding, pixel sampling, missed
edge points and camera calibration affect accuracy. Unsampled corners and hidden
end-face defects are not inspected; zero residual is not proof of a perfect cleave.

The raw pixel measurements, fitted/ideal endpoints, sample count and coverage are
included in the existing session measurement JSON exports under `cleaves`.
These measurements do not change motor calibration, movement, or UV control.

Test: `python3 -m unittest discover -s checks -p test_cleave_geometry.py`
