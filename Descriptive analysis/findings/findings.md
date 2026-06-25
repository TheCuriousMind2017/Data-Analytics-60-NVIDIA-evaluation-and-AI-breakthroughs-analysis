# Descriptive Findings

A consolidated read of the eleven descriptive charts, organised by section, followed by an era-by-era synthesis and a map from charts to research questions. The companion figures live in `../figures/` and the chart-by-chart code in `../descriptive_analysis.ipynb`.

> **Non-causal framing.** Everything below describes *temporal alignment*: where a shift in one of NVIDIA's series lines up in time with an AI milestone. It is not a claim that the milestone caused the shift. The formal structural-break tests are reserved for the diagnostic notebook.

Eras: Pre-Attention / CNN (2010Q1 to 2017Q2), Transformer (2017Q3 to 2022Q3), Generative-AI (2022Q4 to 2026Q1). Milestone markers: AlexNet (2012Q3, inside the first band), Attention/Transformer (2017Q3), ChatGPT (2022Q4).

---

## Headline synthesis

Read era by era, the story is consistent across every series. In the **Pre-Attention / CNN** era NVIDIA is a mid-sized, gaming-led, cyclical chip company: below the market in relative strength, a single-digit share of the three-firm revenue pool, and middling margins. Through the **Transformer** era price, revenue, and margins all begin to lift and NVIDIA pulls ahead of the market, but it is still the smaller firm in absolute revenue. In the **Generative-AI** era every series inflects together: price goes near-vertical, Data Center overtakes Gaming, revenue passes Intel's, the margin and revenue-share orderings reverse, and NVIDIA's capture of hyperscaler capex recovers to a majority share. The single cleanest temporal alignment in the study is Data Center overtaking Gaming in calendar 2022, the ChatGPT year.

---

## Section 1: NVIDIA's own story

### 01. Price (linear and log)
NVIDIA's split-adjusted price is shown on two scales. On the linear panel the series is nearly flat for the first decade and then turns close to vertical from 2023, peaking near \$207 before settling around \$174 at the 2026Q1 cut. The log panel tells a different and arguably more honest story: instead of a single late spike, it shows a sustained multi-year climb that begins lifting in the mid-2010s and steepens through each successive era. As a cumulative index from a 2010 base of 100, the price ends the Pre-Attention era near 900, the Transformer era near 3,000, and the Generative-AI era above 43,000. From the start of 2010 (\$0.42, split-adjusted) to the 2026Q1 cut (\$174.20) the price gained \$173.77, about 411 times or roughly +41,000 percent; from the end of 2022Q4 (\$14.58), the ChatGPT quarter, to the same cut it gained \$159.62, close to 12 times or about +1,095 percent.

The linear view captures magnitude, making clear that almost all of the dollar appreciation falls inside the Generative-AI band. The log view captures rate, and it lines the steepening up with the earlier Attention/Transformer marker as well, which suggests the acceleration is not purely a 2022 phenomenon. *Caution:* this is split-adjusted price, not market capitalisation or any valuation multiple, and the linear panel can mislead the eye into reading the whole story as a single 2022 event.

### 02. Revenue and net income (lines and nested bars)
Trailing-twelve-month revenue and net income are slow and roughly linear through the Pre-Attention era (ending near \$8B and \$2B), accelerate through the Transformer era (about \$29B and \$6B), and rise steeply in the Generative-AI era to roughly \$216B revenue and \$120B net income. The nested-bar panel shows net income filling a steadily larger fraction of each revenue bar, so profitability deepens at the same time as revenue grows.

This is the same inflection visible in price (01) and margins (04), and the revenue series here is the raw material for the structural-break tests in the diagnostic notebook. *Caution:* the series are trailing-twelve-month, so they are smoothed and lag the underlying quarter by up to a year.

### 03. Segments
Through the mid-2010s Gaming is the largest band by a wide margin (for example \$3.0B Gaming against \$0.8B Data Center in 2016). Data Center then overtakes Gaming in calendar 2022, at roughly \$15.0B against \$9.1B, before pulling far ahead at \$47.5B in 2023 and \$115.2B in 2024, while Gaming stays roughly flat.

The crossover is the chart's anchor and the cleanest single alignment in the study: calendar 2022 maps to NVIDIA's fiscal 2023 and lines up directly with the ChatGPT marker. *Caution:* segments are annual and hand-collected from 10-K filings, the early years carry a sizeable unallocated band, one Data-Center figure is flagged as a possible transcription duplicate, and a fiscal-to-calendar offset is applied.

### 04. Margin structure
Each annual bar decomposes revenue into four shares that sum to 100 percent (cost of revenue, operating expenses, other, net income), with the cumulative boundaries equal to the gross, operating, and net margins. The net-income share rises from roughly 7 percent in 2010 to about 56 percent in 2025. Aggregated by era, net margin moves 16 to 28 to 54 percent and gross margin 54 to 61 to 72 percent.

The steepest re-rating sits in the Generative-AI band and coincides with the segment shift in 03: as data-center products displace gaming, more of each revenue dollar survives to the bottom line. *Caution:* the three margins are nested and must not be added together, which is why the chart uses a decomposition rather than stacking them.

---

## Section 2: Peer divergence

### 05. Peer price index
Indexed to 100 at 2010 on a log scale, the five series (NVIDIA, AMD, Intel, Nasdaq-100, PHLX Semiconductor Index) move in a broadly similar band for most of the first decade. NVIDIA then separates and pulls decisively ahead, with the gap widening through the Generative-AI era. The divergence opens up before the generative-AI wave and accelerates within it. *Caution:* a log scale compresses the visual gap, index charts are start-date sensitive, and cumulative price performance is not risk-adjusted.

### 06. Relative strength
Dividing NVIDIA's price index by each benchmark's isolates outperformance. NVIDIA spends the early Pre-Attention era below 1.0, falling as low as 0.45 against the Nasdaq-100 in 2013, crosses above 1.0 for good around May 2016, and surges to roughly 32 times the Nasdaq-100 by the Generative-AI era. The genuine outperformance begins around 2016, between the AlexNet and Attention/Transformer markers, rather than waiting for ChatGPT. *Caution:* the metric is a ratio of two indices and inherits their start-date sensitivity.

### 07. Revenue divergence (indexed and absolute)
The indexed panel shows NVIDIA ending roughly fifty times its 2010 revenue against low-single-digit multiples for peers. The absolute panel shows the concrete fact: NVIDIA's trailing revenue passes Intel's for the first time at 2023Q4, after a decade below it. The crossover sits just inside the Generative-AI band and echoes the price divergence (05) and share reversal (10). This levels-based view is what we rely on instead of revenue-growth correlation, which proved too fragile. *Caution:* revenue is smoothed (TTM), indexing flatters the smallest starting company, and Intel and NVIDIA revenues are not like-for-like.

### 08. Return correlation by era
A single Pearson correlation of daily log-returns per era (roughly 900 to 1,900 days per bar). NVIDIA's correlation with Intel falls 0.46 to 0.59 to 0.32, while its correlation with the Nasdaq-100 stays high (about 0.58, 0.81, 0.76) and with AMD stays moderate to high (0.43, 0.71, 0.63). By the Generative-AI era NVIDIA's returns track the market more than twice as closely as they track Intel: decoupling from the legacy peer alongside continued co-movement with the market. *Caution:* one number per era hides within-era timing, and correlation measures co-movement, not relative performance.

### 09. Gross margin by era
Era total gross profit over era total revenue. NVIDIA rises 54 to 61 to 72 percent, AMD rises 35 to 45 to 48 percent, and Intel falls 62 to 56 to 36 percent, so the margin leader in the Pre-Attention era is the laggard by the Generative-AI era. This margin reversal lines up with the revenue and share reversals in 07 and 10. *Caution:* gross margin reflects mix and pricing, not operating efficiency, and the comparison mixes different product markets.

### 10. Revenue share by era
Among the three firms, Intel falls from 84 to 71 to 26 percent, NVIDIA rises from 8 to 17 to 61 percent, and AMD drifts up from 8 to 11 to 13 percent: a near-total reversal, concentrated in the Generative-AI band. This is the most dramatic single picture of competitive repositioning in the study. *Caution, the firmest in the set:* this is share of these three companies' combined revenue, not market share in any real product market. The 84 percent early figure mainly reflects Intel being a far larger company, not holding 84 percent of anything NVIDIA competed for.

---

## Section 3: Capex linkage

### 11. Capex and capture rate
The left panel plots aggregate trailing hyperscaler capital expenditure (Microsoft, Alphabet, Amazon, Meta) against NVIDIA's trailing revenue on a shared dollar scale; the right panel divides the two into a capture rate. Both series rise, with capex above revenue throughout. The capture rate traces a U: roughly 47 percent in 2011, down to about 15 percent around 2019 to 2020, and back to about 57 percent by 2025. NVIDIA was a large fraction of a small early cloud-capex base, fell as hyperscalers scaled non-GPU spending, then recovered sharply as GPUs became central, with the upturn aligning with the ChatGPT marker.

*Caution, several:* the shared scale is deliberate, since an independent dual axis can manufacture alignment; the capture rate is a ratio of total revenue to total capex, not a supply figure; the early values reflect a small denominator; and capex is the only hyperscaler series pulled.

---

## Research-question map

| Research question | Charts |
|---|---|
| **RQ1** Peer correlation and divergence | 05 (price index), 06 (relative strength), 07 (revenue divergence), 08 (return correlation by era) |
| **RQ2** Inflection points in price, revenue, net income | 01 (price), 02 (revenue and net income) set up the series; the structural-break tests are in the diagnostic notebook |
| **RQ3** Revenue mix, margins, competitive share | 03 (segments), 04 (margin structure), 09 (gross margin by era), 10 (revenue share by era) |
| **RQ4** Structural growth versus cyclicality | 01 (price, log panel), 02 (revenue), 06 (relative strength), plus the diagnostic era comparison |
| **RQ5** Milestone timing and demand backdrop | 03 (segment crossover at 2022), 11 (capex and capture rate), plus the synthesis era table |

RQ2 is the bridge to the diagnostic notebook: charts 01 and 02 present the price, revenue, and net-income series, and the diagnostic work tests whether those series contain statistically detectable structural breaks and whether the breaks cluster near the 2017Q3 and 2022Q4 markers.
