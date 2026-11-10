#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Економічний калькулятор сукупної вартості володіння (TCO) та терміну окупності (ROI).
Порівнює традиційні архітектури з рішеннями на базі Машини Кузьміна (МК)
за 6 ключовими галузями: Automotive, Avionics, Medicine, MarTech, Logistics, MilTech.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class CostBreakdown:
    name: str
    c_dev: float      # Витрати на розробку (софт/залізо), USD
    c_tool: float     # Ліцензії на інструменти та САПР, USD
    c_cert: float     # Сертифікація безпеки (ISO 26262, DO-178C тощо), USD
    n_units: int      # Кількість вузлів (тираж)
    c_hw_unit: float  # Собівартість заліза за 1 шт (BOM), USD
    c_energy_5y: float # Витрати на енергію за 5 років на 1 шт, USD
    c_maint_5y: float  # Підтримка та дебаг за 5 років на 1 шт, USD
    c_risk: float     # Залишковий ризик збоїв/аварій, USD

    def total_tco(self) -> float:
        """Розрахунок повного TCO за 5 років."""
        variable_costs = self.n_units * (self.c_hw_unit + self.c_energy_5y + self.c_maint_5y)
        return self.c_dev + self.c_tool + self.c_cert + variable_costs + self.c_risk


@dataclass
class IndustryComparison:
    industry: str
    baseline: CostBreakdown
    kuzmin: CostBreakdown

    def tco_difference(self) -> float:
        """Різниця TCO: Baseline - Kuzmin (позитивне значення означає економію)."""
        return self.baseline.total_tco() - self.kuzmin.total_tco()

    def savings_percent(self) -> float:
        """Відсоток економії від базового TCO."""
        b_tco = self.baseline.total_tco()
        if b_tco == 0:
            return 0.0
        return (self.tco_difference() / b_tco) * 100.0

    def payback_months(self, annual_savings: float) -> float:
        """Орієнтовний термін окупності в місяцях."""
        capex_diff = (self.kuzmin.c_dev + self.kuzmin.c_tool + self.kuzmin.c_cert + self.kuzmin.n_units * self.kuzmin.c_hw_unit) - \
                     (self.baseline.c_dev + self.baseline.c_tool + self.baseline.c_cert + self.baseline.n_units * self.baseline.c_hw_unit)
        if annual_savings <= 0 or capex_diff <= 0:
            return 0.0
        return (capex_diff / annual_savings) * 12.0


def get_industry_profiles() -> List[IndustryComparison]:
    """Повертає еталонні галузеві профілі витрат."""
    profiles = [
        IndustryComparison(
            industry="Automotive",
            baseline=CostBreakdown(
                name="ARM Cortex-R52 + AUTOSAR OS",
                c_dev=250000.0,
                c_tool=45000.0,
                c_cert=300000.0,
                n_units=500,
                c_hw_unit=80.0,
                c_energy_5y=24.0,
                c_maint_5y=360.0,
                c_risk=150000.0
            ),
            kuzmin=CostBreakdown(
                name="FPGA/ASIC Safety Cage на МК",
                c_dev=380000.0,
                c_tool=15000.0,
                c_cert=180000.0,
                n_units=500,
                c_hw_unit=220.0,
                c_energy_5y=9.0,
                c_maint_5y=120.0,
                c_risk=20000.0
            )
        ),
        IndustryComparison(
            industry="Avionics",
            baseline=CostBreakdown(
                name="Двоканальний процесор + DO-178C C/Ada",
                c_dev=600000.0,
                c_tool=80000.0,
                c_cert=850000.0,
                n_units=100,
                c_hw_unit=1200.0,
                c_energy_5y=150.0,
                c_maint_5y=1800.0,
                c_risk=400000.0
            ),
            kuzmin=CostBreakdown(
                name="МК з формальним SMT-доведенням",
                c_dev=750000.0,
                c_tool=30000.0,
                c_cert=450000.0,
                n_units=100,
                c_hw_unit=1800.0,
                c_energy_5y=80.0,
                c_maint_5y=600.0,
                c_risk=50000.0
            )
        ),
        IndustryComparison(
            industry="Medicine",
            baseline=CostBreakdown(
                name="Низькоспоживаючий MCU + SafeRTOS",
                c_dev=320000.0,
                c_tool=40000.0,
                c_cert=420000.0,
                n_units=2000,
                c_hw_unit=35.0,
                c_energy_5y=15.0,
                c_maint_5y=80.0,
                c_risk=250000.0
            ),
            kuzmin=CostBreakdown(
                name="Асинхронне QDI-ядро МК",
                c_dev=490000.0,
                c_tool=20000.0,
                c_cert=220000.0,
                n_units=2000,
                c_hw_unit=55.0,
                c_energy_5y=2.0,
                c_maint_5y=25.0,
                c_risk=30000.0
            )
        ),
        IndustryComparison(
            industry="MarTech",
            baseline=CostBreakdown(
                name="Кластер із 200 серверів Redis/Flink",
                c_dev=180000.0,
                c_tool=25000.0,
                c_cert=20000.0,
                n_units=200,
                c_hw_unit=5000.0,
                c_energy_5y=1200.0,
                c_maint_5y=3000.0,
                c_risk=100000.0
            ),
            kuzmin=CostBreakdown(
                name="4 сервери з PCIe FPGA-картками МК",
                c_dev=280000.0,
                c_tool=15000.0,
                c_cert=10000.0,
                n_units=4,
                c_hw_unit=15000.0,
                c_energy_5y=800.0,
                c_maint_5y=1200.0,
                c_risk=15000.0
            )
        ),
        IndustryComparison(
            industry="Logistics",
            baseline=CostBreakdown(
                name="Центральний сервер Wi-Fi арбітражу AMR",
                c_dev=200000.0,
                c_tool=30000.0,
                c_cert=50000.0,
                n_units=300,
                c_hw_unit=250.0,
                c_energy_5y=60.0,
                c_maint_5y=400.0,
                c_risk=120000.0
            ),
            kuzmin=CostBreakdown(
                name="Децентралізовані UWB-інтерлоки МК",
                c_dev=290000.0,
                c_tool=15000.0,
                c_cert=25000.0,
                n_units=300,
                c_hw_unit=320.0,
                c_energy_5y=20.0,
                c_maint_5y=150.0,
                c_risk=15000.0
            )
        ),
        IndustryComparison(
            industry="MilTech",
            baseline=CostBreakdown(
                name="SDR на Linux/RTOS + зовнішній HSM",
                c_dev=450000.0,
                c_tool=60000.0,
                c_cert=500000.0,
                n_units=150,
                c_hw_unit=1500.0,
                c_energy_5y=200.0,
                c_maint_5y=1200.0,
                c_risk=350000.0
            ),
            kuzmin=CostBreakdown(
                name="Апаратний замок DoD 3000.09 на МК",
                c_dev=580000.0,
                c_tool=25000.0,
                c_cert=260000.0,
                n_units=150,
                c_hw_unit=2200.0,
                c_energy_5y=70.0,
                c_maint_5y=400.0,
                c_risk=40000.0
            )
        ),
        IndustryComparison(
            industry="Gambling",
            baseline=CostBreakdown(
                name="x86 IPC + Linux + GLI-11 софт",
                c_dev=280000.0,
                c_tool=35000.0,
                c_cert=250000.0,
                n_units=1000,
                c_hw_unit=150.0,
                c_energy_5y=45.0,
                c_maint_5y=120.0,
                c_risk=300000.0
            ),
            kuzmin=CostBreakdown(
                name="x86 + CPLD/FPGA FairPlay Arbiter",
                c_dev=350000.0,
                c_tool=15000.0,
                c_cert=110000.0,
                n_units=1000,
                c_hw_unit=190.0,
                c_energy_5y=20.0,
                c_maint_5y=25.0,
                c_risk=15000.0
            )
        ),
        IndustryComparison(
            industry="SportsBetting",
            baseline=CostBreakdown(
                name="Кластер Redis/Kafka + ризик-софт",
                c_dev=300000.0,
                c_tool=40000.0,
                c_cert=50000.0,
                n_units=50,
                c_hw_unit=6000.0,
                c_energy_5y=1500.0,
                c_maint_5y=4000.0,
                c_risk=800000.0
            ),
            kuzmin=CostBreakdown(
                name="4 сервери + FPGA Alveo Risk Gate",
                c_dev=420000.0,
                c_tool=20000.0,
                c_cert=20000.0,
                n_units=4,
                c_hw_unit=20000.0,
                c_energy_5y=800.0,
                c_maint_5y=1500.0,
                c_risk=40000.0
            )
        )
    ]
    return profiles


def print_comparison_table():
    profiles = get_industry_profiles()
    print("=" * 105)
    print(f"{'Галузь':<12} | {'Базовий TCO ($)':<16} | {'МК TCO ($)':<16} | {'Економія ($)':<16} | {'Економія (%)':<14} | {'Статус'}")
    print("=" * 105)
    for p in profiles:
        b_tco = p.baseline.total_tco()
        k_tco = p.kuzmin.total_tco()
        diff = p.tco_difference()
        pct = p.savings_percent()
        status = "Вигідно (ROI+)" if diff > 0 else "Збитково"
        print(f"{p.industry:<12} | {b_tco:>16,.2f} | {k_tco:>16,.2f} | {diff:>16,.2f} | {pct:>13.1f}% | {status}")
    print("=" * 105)


if __name__ == "__main__":
    print("\nРЕЗУЛЬТАТИ ПАРАМЕТРИЧНОЇ ЕКОНОМІЧНОЇ МОДЕЛІ МАШИНИ КУЗЬМІНА (5-РІЧНИЙ ГОРИЗОНТ):")
    print_comparison_table()
