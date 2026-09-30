from app.units import effective_price, parse_size, product_key_for, unit_price


def test_parse_pack_sizes():
    assert parse_size("12 pack x 12 fl oz") == (12.0, "fl oz", 12)
    assert parse_size("2 x 1 gal") == (1.0, "gal", 2)
    assert parse_size("6 pack x 16.9 fl oz") == (16.9, "fl oz", 6)


def test_parse_simple_sizes():
    assert parse_size("5 lb") == (5.0, "lb", 1)
    assert parse_size("18 ct") == (18.0, "ct", 1)
    assert parse_size("2 l") == (2.0, "l", 1)
    assert parse_size("12 roll") == (12.0, "roll", 1)
    assert parse_size("") == (None, None, 1)
    assert parse_size("family size") == (None, None, 1)


def test_unit_price_families():
    up = unit_price(8.49, 12, "fl oz", 12)
    assert up["unit_label"] == "fl oz" and abs(up["unit_price"] - 8.49 / 144) < 1e-4
    up = unit_price(3.29, 1, "lb", 1)
    assert up["unit_label"] == "oz" and up["unit_price_alt"] == 3.29 and up["unit_label_alt"] == "lb"
    up = unit_price(4.99, 1, "gal", 1)
    assert up["unit_label_alt"] == "gal" and up["unit_price_alt"] == 4.99
    up = unit_price(5.0, 100, "ct", 1)
    assert up["unit_label_alt"] == "100 ct" and up["unit_price_alt"] == 5.0
    assert unit_price(1.0, None, None)["unit_price"] is None


def test_effective_price_deals():
    assert effective_price(8.49, deal_type="bogo") == 4.25
    assert effective_price(8.49, deal_type="multibuy", deal_qty=3, deal_price=19.0) == 6.33
    assert effective_price(12.97, deal_type="coupon", deal_price=3.0) == 9.97
    assert effective_price(3.29, sale_price=2.99) == 2.99
    assert effective_price(3.29, sale_price=3.99) == 3.29  # never worse than list price


def test_product_key_is_stable():
    k1 = product_key_for("Kraft", "Macaroni & Cheese Dinner Original", 7.25, "oz", 5)
    k2 = product_key_for("kraft", "Macaroni & Cheese Dinner Original", 7.25, "oz", 5)
    assert k1 == k2 == "kraft|macaroni-cheese-dinner-original|5x7-25oz"
