# Measured Platinum

New Mining Finder optimization: MEASURED PLATINUM. Selecting it chooses
Platinum and LASER; existing region, ring, reserve and market filters remain.
Only candidates with a calculable sample-wide percentage are returned.

Stored averageProportion is a hit-only average. The new sample average is
hit average × proportionSamples / total Prospector samples, including probes
without Platinum as zero. If percentage-bearing hits do not match the recorded
hit count, or hits exceed sample count, the sample average remains unknown.
Estimated hotspot/ring evidence is not substituted for a measurement.

Sorting: descending sample-wide average, then descending sample count.
Fewer than 30 probes is labeled SMALL SAMPLE. This is a UI warning threshold,
not a statistical confidence interval or a high-yield certification. Every
sample retains a NOT A YIELD GUARANTEE warning. Result details and hover text
show the denominator and explicitly state that zeros are included.

Existing BEST YIELD ranking is retained. No BGS or overlap data changes.
No automatic deployment, release, commit or push is part of this change.
