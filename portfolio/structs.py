from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AccountTypeData:
    current: Decimal = Decimal('0.00')
    target: Decimal = Decimal('0.00')
    variance: Decimal = Decimal('0.00')


@dataclass
class AssetClassEntry:
    account_types: dict[str, AccountTypeData] = field(default_factory=lambda: defaultdict(AccountTypeData))
    total: Decimal = Decimal('0.00')
    target_total: Decimal = Decimal('0.00')
    variance_total: Decimal = Decimal('0.00')


@dataclass
class CategoryEntry:
    asset_classes: dict[str, AssetClassEntry] = field(default_factory=lambda: defaultdict(AssetClassEntry))
    total: Decimal = Decimal('0.00')
    target_total: Decimal = Decimal('0.00')
    variance_total: Decimal = Decimal('0.00')
    account_type_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))


@dataclass
class GroupEntry:
    label: str = ''
    categories: OrderedDict[str, CategoryEntry] = field(default_factory=OrderedDict)
    total: Decimal = Decimal('0.00')
    target_total: Decimal = Decimal('0.00')
    variance_total: Decimal = Decimal('0.00')
    account_type_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    asset_class_count: int = 0


@dataclass
class PortfolioSummary:
    categories: dict[str, CategoryEntry] = field(default_factory=lambda: defaultdict(CategoryEntry))
    groups: dict[str, GroupEntry] = field(default_factory=lambda: defaultdict(GroupEntry))
    grand_total: Decimal = Decimal('0.00')
    grand_target_total: Decimal = Decimal('0.00')
    grand_variance_total: Decimal = Decimal('0.00')
    account_type_grand_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_grand_target_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_grand_variance_totals: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    account_type_percentages: dict[str, Decimal] = field(default_factory=dict)
    category_labels: dict[str, str] = field(default_factory=dict)
    group_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedHolding:
    ticker: str
    name: str
    asset_class: str
    category_code: str
    shares: Decimal = Decimal('0.00')
    current_price: Decimal | None = None
    value: Decimal = Decimal('0.00')  # Current Value
    current_allocation: Decimal = Decimal('0.00')
    target_value: Decimal = Decimal('0.00')
    target_allocation: Decimal = Decimal('0.00')
    target_shares: Decimal = Decimal('0.00')
    value_variance: Decimal = Decimal('0.00')
    allocation_variance: Decimal = Decimal('0.00')
    shares_variance: Decimal = Decimal('0.00')


@dataclass
class HoldingsCategory:
    label: str
    total: Decimal = Decimal('0.00')
    total_target_value: Decimal = Decimal('0.00')
    total_value_variance: Decimal = Decimal('0.00')
    total_current_allocation: Decimal = Decimal('0.00')
    total_target_allocation: Decimal = Decimal('0.00')
    total_allocation_variance: Decimal = Decimal('0.00')
    holdings: list[AggregatedHolding] = field(default_factory=list)


@dataclass
class HoldingsGroup:
    label: str
    total: Decimal = Decimal('0.00')
    total_target_value: Decimal = Decimal('0.00')
    total_value_variance: Decimal = Decimal('0.00')
    total_current_allocation: Decimal = Decimal('0.00')
    total_target_allocation: Decimal = Decimal('0.00')
    total_allocation_variance: Decimal = Decimal('0.00')
    categories: OrderedDict[str, HoldingsCategory] = field(default_factory=OrderedDict)


@dataclass
class HoldingsSummary:
    grand_total: Decimal = Decimal('0.00')
    grand_target_value: Decimal = Decimal('0.00')
    grand_value_variance: Decimal = Decimal('0.00')
    grand_current_allocation: Decimal = Decimal('0.00')
    grand_target_allocation: Decimal = Decimal('0.00')
    grand_allocation_variance: Decimal = Decimal('0.00')
    holding_groups: OrderedDict[str, HoldingsGroup] = field(default_factory=OrderedDict)
