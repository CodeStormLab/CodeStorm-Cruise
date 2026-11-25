{
    'name': 'Codestorm Cruise',
    'version': '19.0.1.0.0',
    'summary': 'Gestione Cruise Codestorm',
    'author': 'Codestorm',
    'license': 'LGPL-3',
    'depends': ['base', 'base_import'],
    'data': [
        'security/ir.model.access.csv',
        'views/cruises_views.xml',
        'views/cruises_stops_views.xml',
        'views/ships_views.xml',
        'views/ports_views.xml',
    ],
    'application': True,
    'installable': True,
}
