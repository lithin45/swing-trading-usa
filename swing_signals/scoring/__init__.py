"""Scoring engine (research file 10).

Weighted-average composite over per-stock factor sub-scores, wrapped by hard
gates (regime + risk) and an agreement/conflict check, producing a transparent
signal with full per-factor attribution. The full pipeline (gates, ATR levels,
agreement) lands in Stage 4; this stage provides the composite seam.
"""
