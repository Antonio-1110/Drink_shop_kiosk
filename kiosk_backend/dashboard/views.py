from django.contrib import admin
from django.shortcuts import render

from operation.models import Shop

from . import data

STOCK_CHARTED = 12  # the rest are in the table under the chart
# what the signed-in staff member may change, so the page only offers what will work
CAN = {
    'orders': 'ordering.change_order',
    'refunds': 'checkout.change_paymentattempt',
    'stock': 'operation.change_inventory',
    'add_drink': 'operation.add_drink', 'drinks': 'operation.change_drink',
    'ingredients': 'operation.change_ingredient', 'kiosks': 'operation.change_kiosk',
    'designer': 'operation.change_designerconfig', 'shops': 'operation.change_shop',
}


def dashboard(request):
    """Charts of orders, sales, stock and fridge temperatures for staff. Opened from the admin."""
    shops = Shop.objects.order_by('name')
    shop = shops.filter(pk=request.GET.get('shop')).first() if request.GET.get('shop', '').isdigit() else None
    days = int(request.GET['days']) if request.GET.get('days') in map(str, data.PERIODS) else 30
    numbers = data.build(shop=shop, days=days)
    charts = {
        'daily': [{'date': row['date'].isoformat(), 'revenue': float(row['revenue']),
                   **{status: row[status] for status in data.S.values}} for row in numbers['daily']],
        'hourly': numbers['hourly'],
        'drinks': [{'name': d['name'], 'cups': d['cups']} for d in numbers['drinks']],
        'grades': numbers['grades'],
        'cancellations': numbers['cancellations'],
        'stock': [{'name': f"{row['ingredient']}" if shop else f"{row['ingredient']} · {row['shop']}",
                   'days_left': float(row['days_left'])}
                  for row in numbers['stock'] if row['days_left'] is not None][:STOCK_CHARTED],
        'temperatures': [{'name': t['name'], 'max_c': float(t['max_c']) if t['max_c'] is not None else None,
                          'points': [[p['at'].isoformat(), float(p['temp_c'])] for p in t['points']]}
                         for t in numbers['temperatures']],
    }
    return render(request, 'admin/dashboard.html', {
        **admin.site.each_context(request),
        'title': 'Dashboard',
        'shops': shops, 'shop': shop, 'days': days, 'periods': data.PERIODS,
        'n': numbers, 'charts': charts, 'stock_charted': len(charts['stock']),
        'return_query': '?' + request.GET.urlencode() if request.GET else '',
        'can': {name: request.user.has_perm(perm) for name, perm in CAN.items()},
    })
