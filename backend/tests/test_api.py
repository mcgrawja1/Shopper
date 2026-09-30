def _select_all(client):
    chains = client.get("/api/stores").json()["chains"]
    ids = [l["id"] for c in chains for l in c["locations"]]
    client.post("/api/stores/locations/select", json={"location_ids": ids, "selected": True})
    return ids


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_search_requires_selected_stores(client):
    chains = client.get("/api/stores").json()["chains"]
    ids = [l["id"] for c in chains for l in c["locations"]]
    client.post("/api/stores/locations/select", json={"location_ids": ids, "selected": False})
    r = client.get("/api/search", params={"item": "sprite"}).json()
    assert r["groups"] == [] and any("No store locations" in w for w in r["warnings"])


def test_search_groups_variants_and_sorts_by_unit_price(client):
    _select_all(client)
    r = client.get("/api/search", params={"item": "sprite"}).json()
    sizes = {v["size_text"] for v in r["variants"]}
    assert {"12 pack x 12 fl oz", "24 pack x 12 fl oz", "30 pack x 12 fl oz"} <= sizes
    ups = [g["best"]["unit_price"] for g in r["groups"]]
    assert ups == sorted(ups)
    for g in r["groups"]:
        offer_ups = [o["unit_price"] for o in g["offers"] if o["in_stock"]]
        assert offer_ups == sorted(offer_ups)


def test_brand_and_size_filters(client):
    _select_all(client)
    r = client.get("/api/search", params={"brand": "Kraft", "item": "mac and cheese", "size": "5 pack"}).json()
    top = r["groups"][0] if r["query"]["size"] else None
    kraft = [g for g in r["groups"] if g["brand"] == "Kraft"]
    assert kraft, "Kraft products should match"
    rel = client.get("/api/search", params={"brand": "Kraft", "item": "mac and cheese", "size": "5 pack", "sort": "relevance"}).json()
    assert rel["groups"][0]["brand"] == "Kraft" and rel["groups"][0]["pack_count"] == 5


def test_bogo_effective_price(client):
    _select_all(client)
    r = client.get("/api/search", params={"item": "sprite", "size": "12 pack"}).json()
    wd = [o for o in r["offers"] if o["chain_slug"] == "winn-dixie" and o["pack_count"] == 12 and o["size_value"] == 12]
    assert wd and wd[0]["deal"]["type"] == "bogo" and abs(wd[0]["effective_price"] - wd[0]["price"] / 2) < 0.011


def test_location_filter(client):
    ids = _select_all(client)
    r = client.get("/api/search", params={"item": "bananas", "locations": str(ids[0])}).json()
    assert {o["location_id"] for o in r["offers"]} == {ids[0]}


def test_autocomplete(client):
    r = client.get("/api/autocomplete", params={"field": "item", "q": "maca"}).json()
    assert any("Macaroni" in x["value"] for x in r)
    r = client.get("/api/autocomplete", params={"field": "brand", "q": "kra"}).json()
    assert r[0]["value"] == "Kraft"


def test_list_lifecycle_and_favorites(client):
    _select_all(client)
    client.delete("/api/lists/current")
    r = client.get("/api/search", params={"item": "bananas"}).json()
    best = r["groups"][0]["best"]
    l = client.post("/api/lists/current/items", json={"offer": best, "qty": 3}).json()
    assert l["breakdown"]["item_count"] == 3 and l["breakdown"]["total"] == round(best["effective_price"] * 3, 2)
    assert l["breakdown"]["stores"][0]["aisles"][0]["aisle"] == best["aisle"]
    # adding the same offer again merges quantities
    l = client.post("/api/lists/current/items", json={"offer": best, "qty": 1}).json()
    assert l["items"][0]["qty"] == 4
    # favorites auto-populate
    favs = client.get("/api/favorites").json()
    assert any(f["product_key"] == best["product_key"] and f["times_added"] >= 2 for f in favs)
    # patch + save + load
    item_id = l["items"][0]["item_id"]
    l = client.patch(f"/api/lists/current/items/{item_id}", json={"qty": 2, "checked": True}).json()
    assert l["items"][0]["qty"] == 2 and l["items"][0]["checked"] is True
    saved = client.post("/api/lists/current/save", json={"name": "Test list"}).json()
    assert saved["is_draft"] is False and saved["items"][0]["qty"] == 2
    cur = client.get("/api/lists/current").json()
    assert cur["source_list_id"] == saved["id"] and cur["name"] == "Test list"
    client.delete("/api/lists/current")
    assert client.get("/api/lists/current").json()["items"] == []
    loaded = client.post(f"/api/lists/{saved['id']}/load", params={"regenerate": "true"}).json()
    assert loaded["items"][0]["qty"] == 2 and loaded["changes"][0]["status"] == "updated"
    lists = client.get("/api/lists").json()
    assert any(x["id"] == saved["id"] for x in lists)
    client.delete(f"/api/lists/{saved['id']}")
    assert not any(x["id"] == saved["id"] for x in client.get("/api/lists").json())


def test_regenerate_moves_to_cheapest(client):
    _select_all(client)
    client.delete("/api/lists/current")
    r = client.get("/api/search", params={"brand": "Lay's", "item": "potato chips", "sort": "price"}).json()
    g = [g for g in r["groups"] if g["brand"] == "Lay's"][0]
    worst = g["offers"][-1]
    client.post("/api/lists/current/items", json={"offer": worst, "qty": 1})
    out = client.post("/api/lists/current/regenerate", json={"strategy": "cheapest"}).json()
    ch = out["changes"][0]
    assert ch["status"] == "updated" and ch["new_price"] <= ch["old_price"]
    out = client.post("/api/lists/current/regenerate", json={"strategy": "same_store"}).json()
    assert out["changes"][0]["moved"] is False


def test_deals_endpoints(client):
    _select_all(client)
    d = client.get("/api/deals").json()["deals"]
    assert d and all(x["deal"] for x in d) and d[0]["savings_pct"] >= d[-1]["savings_pct"]
    client.delete("/api/lists/current")
    r = client.get("/api/search", params={"item": "sprite", "size": "12 pack", "sort": "price"}).json()
    g = [g for g in r["groups"] if g["brand"] == "Sprite" and g["pack_count"] == 12][0]
    no_deal = [o for o in g["offers"] if not o["deal"]][-1]
    client.post("/api/lists/current/items", json={"offer": no_deal, "qty": 2})
    recs = client.get("/api/deals/for-list").json()["recommendations"]
    assert recs and recs[0]["deal"]["deal"] and recs[0]["savings_total"] > 0


def test_settings_and_accounts(client):
    s = client.put("/api/settings", json={"home_zip": "32504", "default_sort": "price"}).json()
    assert s["home_zip"] == "32504" and s["default_sort"] == "price"
    a = client.post("/api/settings/accounts", json={"program": "Winn-Dixie Rewards", "kind": "rewards", "chain_slug": "winn-dixie"}).json()
    assert a["id"]
    assert any(x["id"] == a["id"] for x in client.get("/api/settings").json()["accounts"])
    client.delete(f"/api/settings/accounts/{a['id']}")


def test_user_added_location(client):
    loc = client.post("/api/stores/walmart/locations", json={"name": "Walmart - Test St", "zip": "00000"}).json()
    assert loc["selected"] == 1 and loc["user_added"] == 1
    r = client.get("/api/search", params={"item": "bananas", "locations": str(loc["id"])}).json()
    assert r["offers"] and r["offers"][0]["location_name"] == "Walmart - Test St"
    client.delete(f"/api/stores/locations/{loc['id']}")


def test_lookup(client):
    _select_all(client)
    r = client.get("/api/search", params={"item": "bananas"}).json()
    key = r["groups"][0]["product_key"]
    lk = client.get("/api/lookup", params={"product_key": key}).json()
    assert lk["offers"] and all(o["product_key"] == key for o in lk["offers"])
