"""Tests for expanded farmer profile payload."""

from __future__ import annotations

from services.farmer_dashboard_service import get_farmer_profile


def test_profile_includes_general_metadata():
    profile = get_farmer_profile(sectors=["dairy", "beef", "lamb"])
    assert profile["county"]
    assert profile["herd_number"]
    assert profile["total_hectares"] == 185
    assert profile["owner_name"]
    assert profile["land_by_sector"]["dairy"] == 72
    assert profile["land_by_sector"]["beef"] == 68
    assert profile["land_by_sector"]["lamb"] == 45


def test_profile_sector_blocks_when_all_selected():
    profile = get_farmer_profile(sectors=["dairy", "beef", "lamb"])
    sectors = profile["sector_profile"]
    assert "dairy" in sectors
    assert "beef" in sectors
    assert "lamb" in sectors
    assert sectors["dairy"]["milking_cows"]
    assert sectors["dairy"]["milk_solids_bonus_per_litre"] == 0.018
    assert sectors["dairy"]["dry_cows"] == 12
    assert sectors["beef"]["cattle_on_farm"]
    assert sectors["beef"]["finishing_units"] == 28
    assert sectors["lamb"]["ewes"]
    assert sectors["lamb"]["lambs_on_farm"] == 180


def test_profile_omits_unselected_sectors():
    profile = get_farmer_profile(sectors=["dairy"])
    sectors = profile["sector_profile"]
    assert "dairy" in sectors
    assert "beef" not in sectors
    assert "lamb" not in sectors
