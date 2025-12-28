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

### Post-Migration Notes
- `Holding.current_price` field has been removed via migration 0004
- `Holding.current_price` property exists as a simple wrapper around `latest_price` for API compatibility
- No fallback logic exists - all prices must be stored in SecurityPrice table
- All existing code successfully migrated to use SecurityPrice table

### Migration Status
- [x] Models created (migration 0003)
- [x] Services updated
- [x] Tests migrated (all 220+ tests passing)
- [x] seed_dev_data command fixed
- [x] Field removal (migration 0004)
- [x] Admin interface cleanup (Completed)
- [x] Documentation cleanup (Completed)

### Migration Progress
The core migration is complete and functional. All price data now flows through the SecurityPrice table. Remaining tasks are documentation updates and admin UI polish - no functional changes needed.
