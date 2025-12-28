# Preparatory Refactoring Log

## [Migration] Centralized Price Table

### Context
Moving price storage from `Holding` table to `SecurityPrice` table to support historical prices and reproducible rebalancing.

### Changes
1. **New Model**: `SecurityPrice` added to `portfolio.models`.
   - Fields: `security`, `price`, `price_datetime` (market time), `fetched_at` (audit time), `source`.
   - Unique constraint on `(security, price_datetime)`.

2. **Holding Model Updates**:
   - Added `latest_price` property (reads from `SecurityPrice`, falls back to `current_price`).
   - Added `price_as_of_date` property.
   - Updated `market_value` to use `latest_price`.

3. **Service Updates**:
   - `MarketDataService.get_prices` now returns `(price, timestamp)` tuples.
   - `PricingService` now writes to `SecurityPrice` table.

### Backward Compatibility
- `Holding.current_price` is still updated by `PricingService` for temporary backward compatibility.
- `Holding.latest_price` falls back to `current_price` if no `SecurityPrice` is found.

### Migration Status
- [x] Models created
- [x] Services updated
- [x] Tests added
- [ ] Admin updated (In Progress)
- [ ] Verification (Pending)
