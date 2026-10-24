# Hand spot-checks

Three dates checked by hand against the raw settlement file. The same values are asserted in `test_spot_checks.py`,
which runs whenever `data/raw/` is present.

## 5-Feb-2018 (Volmageddon)

- Live contracts after the close: VXG18 (expiry 14-Feb) 33.225, VXH18 27.975, VXJ18 24.725. Spot VIX was 37.32.
- VX1 = VXG18, VX2 = VXH18, so the slope is 27.975 − 33.225 = **−5.25**. The curve is inverted.
- Contango = 27.975 / 33.225 − 1 = **−15.8%**. Basis = 33.225 − 37.32 = **−4.095**.
- Business days to VXG18 expiry: 6, 7, 8, 9, 12, 13, 14 Feb = 7, which is more than 5, so the held contract is VXG18.
- VXG18 settled 15.625 on 2-Feb and 33.225 on 5-Feb. A 1-lot short lost (33.225 − 15.625) × $1,000 = **−$17,600**.
  This is the worst day of "Short front, always" in the summary table.
- Signal: the curve closed inverted, so every filtered strategy wants to be flat. The exit trades at the next settle
  (6-Feb), and the strategy is flat from then on.

## 16-Mar-2020 (Covid)

- VXH20 (expiry 18-Mar) 72.625, VXJ20 59.15. Spot VIX was 82.69.
- VXH20 has 2 business days left, so the roll rule (> 5 days) means the held contract is **VXJ20**, not VX1.
- VXJ20 went from 43.90 on 13-Mar to 59.15. A 1-lot short lost **−$15,250** that day.

## 5-Aug-2024 (yen carry unwind)

- VXQ24 (expiry 21-Aug) 32.0986, VXU24 30.3911. Spot VIX was 38.57.
- Business days to expiry: 12, so the held contract is VXQ24.
- VXQ24 went from 21.8527 on 2-Aug to 32.0986. A 1-lot short lost **−$10,245.90**. The filtered strategies that were
  short on 2-Aug take this whole gap: the exit is only decided at the 5-Aug close, which is why "an overnight gap
  still costs" appears in the tail chart.

## Costs (test_maths.py)

- VX: 1 tick = 0.05 × $1,000 = $50, plus $2.50 commission = **$52.50 per contract per side**. A roll trades two
  contracts.
- SR3: 1 tick = 0.5 bp × $25 = $12.50, plus $2.50 = $15 per side, so **$30 per round trip**.
