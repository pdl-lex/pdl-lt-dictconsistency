import reflex as rx

config = rx.Config(
    app_name="pdl_lt_dictconsistency",
    backend_host="0.0.0.0",
    frontend_path="/dictconsistency",
    # api_url="/dictconsistency",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)
