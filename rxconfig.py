import reflex as rx

config = rx.Config(
    app_name="pdl_ltlabtools_dictconsistency",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)