from django.contrib import admin
from django.shortcuts import render

from operation.models import Shop

from . import data

STOCK_CHARTED = 12  # the rest are in the table under the chart


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
        'drinks': numbers['drinks'],
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
    })
