#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модульні тести для економічного калькулятора TCO (economic-model/tco_calculator.py).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tco_calculator import CostBreakdown, IndustryComparison, get_industry_profiles


class TestTcoCalculator(unittest.TestCase):

    def test_cost_breakdown_total(self):
        cb = CostBreakdown(
            name="Test Node",
            c_dev=100.0,
            c_tool=50.0,
            c_cert=50.0,
            n_units=10,
            c_hw_unit=10.0,
            c_energy_5y=2.0,
            c_maint_5y=3.0,
            c_risk=20.0
        )
        # Variable = 10 * (10 + 2 + 3) = 150
        # Fixed = 100 + 50 + 50 + 20 = 220
        # Total = 370
        self.assertEqual(cb.total_tco(), 370.0)

    def test_industry_profiles_positive_savings(self):
        profiles = get_industry_profiles()
        self.assertEqual(len(profiles), 8)
        for p in profiles:
            self.assertGreater(p.baseline.total_tco(), 0)
            self.assertGreater(p.kuzmin.total_tco(), 0)
            # In all selected sweet-spot niches, Kuzmin machine provides net 5-year savings
            self.assertGreater(p.tco_difference(), 0, f"Failed for {p.industry}")
            self.assertGreater(p.savings_percent(), 15.0, f"Expected >15% savings in {p.industry}")

    def test_martech_high_capex_savings(self):
        profiles = {p.industry: p for p in get_industry_profiles()}
        martech = profiles["MarTech"]
        # MarTech replaces 200 servers with 4 servers, savings must be significant (> $1M)
        self.assertGreater(martech.tco_difference(), 1_000_000.0)


if __name__ == "__main__":
    unittest.main()
