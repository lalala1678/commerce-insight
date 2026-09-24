from datetime import date
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .db import make_engine
from .metrics import overview
from . import analytics, customers, reports

def create_app(db=None):
    app=FastAPI(title='商析 · 电商经营分析平台',version='0.3.0')
    database=db if db is not None else make_engine()

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request,exception):
        detail = '数据库尚未就绪。请检查连接并先执行 python -m backend.etl。'
        if request.url.path == '/api/overview':
            detail = '合成数据尚未就绪。请先执行 python -m backend.seed。'
        return JSONResponse(status_code=503,content={'detail':detail})

    @app.exception_handler(analytics.WarehouseNotReady)
    async def unimported(request, exception):
        return JSONResponse(status_code=503, content={'detail': '真实数据尚未导入。请先执行 python -m backend.etl。'})

    @app.exception_handler(ValueError)
    async def invalid_range(request, exception):
        return JSONResponse(status_code=422, content={'detail': str(exception)})

    def filters(start: date = date(2018, 7, 1), end: date = date(2018, 7, 31),
                category: str = Query('', max_length=128), state: str = Query('', max_length=10)):
        return {'start': start, 'end': end, 'category': category, 'state': state}

    @app.get('/api/health')
    def health():
        with analytics.read_snapshot(database) as conn:
            conn.execute(text('SELECT 1'))
            try:
                analytics._meta(conn)
                ready = True
            except analytics.WarehouseNotReady:
                ready = False
        return {'status':'ok','database':database.dialect.name,'stage':'core','warehouse_ready':ready}

    @app.get('/api/overview', deprecated=True)
    def get_overview():return overview(database)

    @app.get('/api/options')
    def get_options():
        return analytics.options(database)

    @app.get('/api/dashboard')
    def get_dashboard(scope: dict = Depends(filters), grain: Literal['day', 'week', 'month'] = 'day'):
        return analytics.dashboard(database, **scope, grain=grain)

    @app.get('/api/orders')
    def get_orders(scope: dict = Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return analytics.orders(database, **scope, page=page, page_size=page_size)

    @app.get('/api/customers')
    def get_customers(scope: dict = Depends(filters)):
        return customers.customer_analysis(database, **scope)

    @app.get('/api/reports')
    def get_report(scope: dict = Depends(filters), format: Literal['json', 'markdown', 'html'] = 'json'):
        result = reports.build_report(database, **scope)
        if format == 'json':
            return {**result, 'rendered': {'markdown': reports.markdown(result), 'html': reports.html_report(result)}}
        content = reports.markdown(result) if format == 'markdown' else reports.html_report(result)
        ext = 'md' if format == 'markdown' else 'html'
        filename = f"commerce-report-{result['meta']['start']}-{result['meta']['end']}.{ext}"
        return Response(content, media_type='text/markdown' if format == 'markdown' else 'text/html',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    @app.get('/api/orders/{order_id}')
    def get_order(order_id: str, category: str = Query('', max_length=128)):
        result = analytics.order_details(database, order_id, category)
        if result is None:
            raise HTTPException(status_code=404, detail='未找到符合条件的已交付订单。')
        return result

    return app

app=create_app()
