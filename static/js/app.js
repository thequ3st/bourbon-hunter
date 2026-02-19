// PA Bourbon Hunter — Dashboard JavaScript

(function () {
    "use strict";

    // State
    let allBourbons = [];
    let inventory = [];
    let nearbyInventory = null; // null = not in nearby mode, [] = nearby mode active
    let userLocation = null; // { lat, lng, zip, radius }
    let currentTierFilter = "all";
    let currentShowFilter = "all";
    let searchQuery = "";
    let scanPollInterval = null;

    // DOM refs
    const grid = document.getElementById("bourbon-grid");
    const scanBanner = document.getElementById("scan-banner");
    const scanBannerText = document.getElementById("scan-banner-text");
    const modalOverlay = document.getElementById("modal-overlay");
    const modalContent = document.getElementById("modal-content");

    // ---- Init ----
    document.addEventListener("DOMContentLoaded", init);

    async function init() {
        await Promise.all([loadBourbons(), loadStats(), loadScanHistory()]);
        loadInventory();
        setupFilters();
        setupSearch();
        setupScanButtons();
        setupModal();
        setupLocationFilter();
        pollScanStatus();
    }

    // ---- Data Loading ----

    async function loadBourbons() {
        try {
            const resp = await fetch("/api/bourbons");
            allBourbons = await resp.json();
            renderGrid();
        } catch (e) {
            grid.innerHTML = '<div class="empty-state">Failed to load bourbon database</div>';
        }
    }

    async function loadInventory() {
        try {
            const resp = await fetch("/api/inventory");
            inventory = await resp.json();
            renderGrid(); // Re-render with stock info
            renderRecentFinds();
        } catch (e) {
            console.error("Failed to load inventory:", e);
        }
    }

    async function loadStats() {
        try {
            const resp = await fetch("/api/stats");
            const stats = await resp.json();
            document.getElementById("stat-tracked").textContent = stats.knowledge_base?.total || "—";
            document.getElementById("stat-in-stock").textContent = stats.in_stock || 0;
            document.getElementById("stat-alerts").textContent = stats.alerts_today || 0;

            if (stats.last_scan?.completed_at) {
                const d = new Date(stats.last_scan.completed_at + "Z");
                document.getElementById("stat-last-scan").textContent = formatTimeAgo(d);
            } else {
                document.getElementById("stat-last-scan").textContent = "Never";
            }
        } catch (e) {
            console.error("Failed to load stats:", e);
        }
    }

    async function loadScanHistory() {
        try {
            const resp = await fetch("/api/scan/history");
            const history = await resp.json();
            const tbody = document.getElementById("scan-table-body");

            if (history.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No scans yet</td></tr>';
                return;
            }

            tbody.innerHTML = history.map(scan => {
                const time = scan.started_at ? new Date(scan.started_at + "Z").toLocaleString() : "—";
                const statusClass = scan.status === "completed" ? "tier4" :
                                    scan.status === "error" ? "tier1" : "accent-gold";
                return `<tr>
                    <td>${time}</td>
                    <td>${scan.scan_type}</td>
                    <td style="color: var(--${statusClass})">${scan.status}</td>
                    <td>${scan.products_found || 0}</td>
                    <td>${scan.new_finds || 0}</td>
                </tr>`;
            }).join("");
        } catch (e) {
            console.error("Failed to load scan history:", e);
        }
    }

    // ---- Rendering ----

    function renderGrid() {
        const filtered = filterBourbons();
        if (filtered.length === 0) {
            grid.innerHTML = '<div class="empty-state">No bourbons match your filters</div>';
            return;
        }

        grid.innerHTML = filtered.map(b => {
            const tier = b.rarity_tier;
            const stockInfo = getStockInfo(b.id);
            const hasStock = stockInfo.length > 0;
            const cardClass = hasStock ? `bourbon-card--t${tier} bourbon-card--in-stock` : `bourbon-card--t${tier}`;

            const imgUrl = b.image_url || getStockImage(b.id);

            return `
            <div class="bourbon-card ${cardClass}" data-bourbon-id="${b.id}">
                <div class="bourbon-card__body">
                    ${imgUrl ? `<div class="bourbon-card__img"><img src="${esc(imgUrl)}" alt="" loading="lazy"></div>` : ""}
                    <div class="bourbon-card__info">
                <div class="bourbon-card__header">
                    <span class="bourbon-card__name">${esc(b.name)}</span>
                    ${b.average_rating ? `<span class="rating">${b.average_rating}</span>` : ""}
                </div>
                <div class="bourbon-card__distillery">${esc(b.distillery || "")}</div>
                <div class="bourbon-card__meta">
                    <span class="tier-badge tier-badge--${tier}">${esc(b.tier_label || tierLabel(tier))}</span>
                    ${b.proof ? `<span class="bourbon-card__tag">${b.proof} proof</span>` : ""}
                    ${b.age ? `<span class="bourbon-card__tag">${esc(b.age)}</span>` : ""}
                    ${b.msrp ? `<span class="bourbon-card__tag">MSRP $${b.msrp}</span>` : ""}
                </div>
                ${b.notes ? `<div class="bourbon-card__notes">${esc(b.notes)}</div>` : ""}
                <div class="bourbon-card__stock-status">
                    <span class="stock-dot ${hasStock ? 'stock-dot--in' : 'stock-dot--out'}"></span>
                    ${hasStock
                        ? nearbyStockLabel(stockInfo)
                        : '<span style="color: var(--text-muted)">Not found in FWGS</span>'
                    }
                </div>
                    </div>
                </div>
            </div>`;
        }).join("");

        // Click handlers
        grid.querySelectorAll(".bourbon-card").forEach(card => {
            card.addEventListener("click", () => {
                const id = card.dataset.bourbonId;
                showBourbonDetail(id);
            });
        });
    }

    function renderRecentFinds() {
        const container = document.getElementById("recent-finds");
        if (inventory.length === 0) {
            container.innerHTML = '<p class="empty-state">No recent finds. Start a scan to check FWGS inventory.</p>';
            return;
        }

        // Show most recent 10 inventory finds
        const recent = inventory.slice(0, 10);
        container.innerHTML = recent.map(inv => {
            const time = inv.scanned_at ? formatTimeAgo(new Date(inv.scanned_at + "Z")) : "—";
            return `
            <div class="timeline-item">
                <span class="timeline-item__time">${time}</span>
                <span class="tier-badge tier-badge--${inv.rarity_tier || 4}">${tierLabel(inv.rarity_tier)}</span>
                <span class="timeline-item__name">${esc(inv.name)}</span>
                <span class="timeline-item__store">${esc(inv.store_name || "")} — Qty: ${inv.quantity}</span>
            </div>`;
        }).join("");
    }

    // ---- Filtering ----

    function filterBourbons() {
        return allBourbons.filter(b => {
            // Tier filter
            if (currentTierFilter !== "all" && b.rarity_tier !== parseInt(currentTierFilter)) return false;
            // In-stock filter
            if (currentShowFilter === "in-stock" && getStockInfo(b.id).length === 0) return false;
            // Nearby filter — only show bourbons with nearby stock
            if (currentShowFilter === "nearby" && nearbyInventory !== null) {
                if (!nearbyInventory.some(inv => inv.bourbon_id === b.id)) return false;
            }
            // Search
            if (searchQuery) {
                const q = searchQuery.toLowerCase();
                const searchable = `${b.name} ${b.distillery || ""} ${b.notes || ""}`.toLowerCase();
                if (!searchable.includes(q)) return false;
            }
            return true;
        });
    }

    function setupFilters() {
        // Tier filters
        document.querySelectorAll("[data-tier]").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll("[data-tier]").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                currentTierFilter = btn.dataset.tier;
                renderGrid();
            });
        });

        // Show filters
        document.querySelectorAll("[data-show]").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll("[data-show]").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                currentShowFilter = btn.dataset.show;

                const locFilter = document.getElementById("location-filter");
                if (btn.dataset.show === "nearby") {
                    locFilter.classList.remove("hidden");
                } else {
                    locFilter.classList.add("hidden");
                    nearbyInventory = null;
                    userLocation = null;
                }
                renderGrid();
            });
        });
    }

    function setupSearch() {
        const input = document.getElementById("search-input");
        let debounce;
        input.addEventListener("input", () => {
            clearTimeout(debounce);
            debounce = setTimeout(() => {
                searchQuery = input.value.trim();
                renderGrid();
            }, 250);
        });
    }

    // ---- Location Filter ----

    function setupLocationFilter() {
        const btnGPS = document.getElementById("btn-use-location");
        const btnSearch = document.getElementById("btn-apply-location");
        const zipInput = document.getElementById("zip-input");
        const statusEl = document.getElementById("location-status");

        btnGPS.addEventListener("click", () => {
            if (!navigator.geolocation) {
                statusEl.textContent = "GPS not supported";
                return;
            }
            statusEl.textContent = "Getting location...";
            btnGPS.disabled = true;
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    btnGPS.disabled = false;
                    const radius = parseInt(document.getElementById("radius-select").value);
                    statusEl.textContent = `Located (${pos.coords.latitude.toFixed(2)}, ${pos.coords.longitude.toFixed(2)})`;
                    loadNearbyInventory({ lat: pos.coords.latitude, lng: pos.coords.longitude, radius });
                },
                (err) => {
                    btnGPS.disabled = false;
                    statusEl.textContent = "Location denied";
                    console.error("Geolocation error:", err);
                },
                { timeout: 10000 }
            );
        });

        btnSearch.addEventListener("click", () => {
            const zip = zipInput.value.trim();
            if (!zip || zip.length < 5) {
                statusEl.textContent = "Enter a 5-digit zip";
                return;
            }
            const radius = parseInt(document.getElementById("radius-select").value);
            statusEl.textContent = "Searching...";
            loadNearbyInventory({ zip, radius });
        });

        zipInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") btnSearch.click();
        });
    }

    async function loadNearbyInventory({ lat, lng, zip, radius }) {
        const statusEl = document.getElementById("location-status");
        try {
            let url = `/api/inventory/nearby?radius=${radius}`;
            if (zip) {
                url += `&zip=${encodeURIComponent(zip)}`;
            } else if (lat != null && lng != null) {
                url += `&lat=${lat}&lng=${lng}`;
            }

            const resp = await fetch(url);
            const data = await resp.json();

            if (!resp.ok) {
                statusEl.textContent = data.error || "Search failed";
                return;
            }

            nearbyInventory = data.inventory || [];
            userLocation = data.location;
            statusEl.textContent = `${data.stores_in_range} stores within ${radius} mi — ${nearbyInventory.length} items`;
            renderGrid();
        } catch (e) {
            statusEl.textContent = "Network error";
            console.error("Nearby inventory error:", e);
        }
    }

    // ---- Scan Controls ----

    function setupScanButtons() {
        document.getElementById("btn-scan-quick").addEventListener("click", () => startScan("quick", 2));
        document.getElementById("btn-scan-full").addEventListener("click", () => startScan("full"));
    }

    async function startScan(type, tier) {
        try {
            const body = { type };
            if (tier) body.tier = tier;
            const resp = await fetch("/api/scan/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await resp.json();

            if (resp.ok) {
                showScanBanner(`Scanning FWGS (${type})...`);
                startScanPolling();
            } else {
                alert(data.error || "Failed to start scan");
            }
        } catch (e) {
            alert("Failed to start scan: " + e.message);
        }
    }

    function showScanBanner(text) {
        scanBannerText.textContent = text;
        scanBanner.classList.remove("hidden");
    }

    function hideScanBanner() {
        scanBanner.classList.add("hidden");
    }

    function startScanPolling() {
        if (scanPollInterval) return;
        scanPollInterval = setInterval(async () => {
            try {
                const resp = await fetch("/api/scan/status");
                const data = await resp.json();
                if (!data.running) {
                    clearInterval(scanPollInterval);
                    scanPollInterval = null;
                    hideScanBanner();
                    // Refresh data
                    await Promise.all([loadBourbons(), loadStats(), loadScanHistory(), loadInventory()]);

                    if (data.last_result?.new_finds > 0) {
                        showScanBanner(`Scan complete! ${data.last_result.new_finds} new find(s)!`);
                        setTimeout(hideScanBanner, 5000);
                    }
                }
            } catch (e) {
                console.error("Poll error:", e);
            }
        }, 3000);
    }

    function pollScanStatus() {
        // Check if a scan is already running on page load
        fetch("/api/scan/status")
            .then(r => r.json())
            .then(data => {
                if (data.running) {
                    showScanBanner("Scan in progress...");
                    startScanPolling();
                }
            })
            .catch(() => {});
    }

    // ---- Modal ----

    function setupModal() {
        document.getElementById("modal-close").addEventListener("click", closeModal);
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) closeModal();
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") closeModal();
        });
    }

    function closeModal() {
        modalOverlay.classList.add("hidden");
    }

    function showBourbonDetail(bourbonId) {
        const bourbon = allBourbons.find(b => b.id === bourbonId);
        if (!bourbon) return;

        const stockInfo = getStockInfo(bourbonId);
        const tier = bourbon.rarity_tier;

        const modalImg = bourbon.image_url || getStockImage(bourbonId);

        let html = `
            <div class="modal__header-row">
                ${modalImg ? `<img class="modal__product-img" src="${esc(modalImg)}" alt="">` : ""}
                <div>
                    <span class="tier-badge tier-badge--${tier}">${tierLabel(tier)}</span>
                    <h2 style="margin-top: 8px;">${esc(bourbon.name)}</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 16px;">${esc(bourbon.distillery || "")}</p>
                </div>
            </div>

            <div class="detail-row">
                <span class="detail-row__label">Proof</span>
                <span class="detail-row__value">${bourbon.proof || "Varies"}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row__label">Age</span>
                <span class="detail-row__value">${bourbon.age || "NAS"}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row__label">MSRP</span>
                <span class="detail-row__value">${bourbon.msrp ? "$" + bourbon.msrp : "N/A"}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row__label">Rating</span>
                <span class="detail-row__value">${bourbon.average_rating ? bourbon.average_rating + "/10" : "N/A"}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row__label">Rating Sources</span>
                <span class="detail-row__value">${(bourbon.rating_sources || []).join(", ") || "None"}</span>
            </div>
            ${bourbon.annual_release ? `
            <div class="detail-row">
                <span class="detail-row__label">Release Window</span>
                <span class="detail-row__value">${bourbon.release_window || "Annual"}</span>
            </div>` : ""}
            ${bourbon.notes ? `
            <div style="margin-top: 16px; padding: 12px; background: var(--bg-card); border-radius: var(--radius); font-size: 0.85rem; color: var(--text-secondary);">
                ${esc(bourbon.notes)}
            </div>` : ""}
        `;

        if (stockInfo.length > 0) {
            const isNearby = currentShowFilter === "nearby" && nearbyInventory !== null;
            const headerLabel = isNearby
                ? `Nearby Stores (${stockInfo.length})`
                : `In Stock (${stockInfo.length} store${stockInfo.length > 1 ? "s" : ""})`;
            html += `
                <h3 style="margin-top: 20px; color: var(--tier4);">${headerLabel}</h3>
                <div class="store-list">
                    ${stockInfo.map(s => `
                        <div class="store-item">
                            <div>
                                <strong>${esc(s.store_name || "Store #" + s.store_number)}</strong>
                                <div style="font-size: 0.75rem; color: var(--text-muted)">${esc(s.store_address || "")}</div>
                                ${s.county ? `<div style="font-size: 0.7rem; color: var(--text-muted)">${esc(s.county)} County</div>` : ""}
                            </div>
                            <div style="text-align: right;">
                                <div style="font-weight: 700; color: var(--tier4)">Qty: ${s.quantity}</div>
                                ${s.distance_miles != null ? `<div style="font-size: 0.8rem; color: var(--accent-gold)">${s.distance_miles} mi</div>` : ""}
                                ${s.price ? `<div style="font-size: 0.8rem;">$${s.price}</div>` : ""}
                            </div>
                        </div>
                    `).join("")}
                </div>
            `;
        } else {
            html += `
                <div style="margin-top: 20px; text-align: center; color: var(--text-muted); padding: 20px;">
                    Not currently found in FWGS inventory.
                    <br>Run a scan to check availability.
                </div>
            `;
        }

        modalContent.innerHTML = html;
        modalOverlay.classList.remove("hidden");
    }

    // ---- Helpers ----

    function getStockImage(bourbonId) {
        const inv = inventory.find(i => i.bourbon_id === bourbonId && i.image_url);
        return inv ? inv.image_url : null;
    }

    function nearbyStockLabel(stockInfo) {
        if (currentShowFilter === "nearby" && nearbyInventory !== null && stockInfo.length > 0) {
            const closest = stockInfo.reduce((a, b) =>
                (a.distance_miles || 999) < (b.distance_miles || 999) ? a : b
            );
            const dist = closest.distance_miles != null ? closest.distance_miles + " mi" : "";
            return `<span style="color: var(--tier4)">In stock at ${stockInfo.length} nearby store${stockInfo.length > 1 ? "s" : ""}${dist ? " — closest " + dist : ""}</span>`;
        }
        return `<span style="color: var(--tier4)">In stock at ${stockInfo.length} store${stockInfo.length > 1 ? "s" : ""}</span>`;
    }

    function getStockInfo(bourbonId) {
        if (currentShowFilter === "nearby" && nearbyInventory !== null) {
            return nearbyInventory.filter(inv => inv.bourbon_id === bourbonId);
        }
        return inventory.filter(inv => inv.bourbon_id === bourbonId);
    }

    function tierLabel(tier) {
        const labels = { 1: "Unicorn", 2: "Highly Allocated", 3: "Allocated", 4: "Worth Tracking" };
        return labels[tier] || "Unknown";
    }

    function esc(str) {
        if (!str) return "";
        const d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }

    function formatTimeAgo(date) {
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);
        if (diff < 60) return "just now";
        if (diff < 3600) return Math.floor(diff / 60) + "m ago";
        if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
        return Math.floor(diff / 86400) + "d ago";
    }
})();
