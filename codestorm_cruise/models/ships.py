from odoo import fields, models


class Ships(models.Model):
    _name = 'codestorm.ships'
    _description = 'Nave'
    _order = 'name'

    name = fields.Char('Nome', required=True)
    codice = fields.Char('Codice IMO', copy=False)
    compagnia_id = fields.Many2one('res.partner', 'Compagnia')
    anno_costruzione = fields.Integer('Anno di costruzione')
    capacita_passeggeri = fields.Integer('Capacità passeggeri')
    stazza_lorda = fields.Float('Stazza lorda (GT)')
    note = fields.Text('Note')
    active = fields.Boolean(default=True)

    cruise_ids = fields.One2many('codestorm.cruises', 'ship_id', 'Crociere')

    _codice_unique = models.Constraint(
        'UNIQUE(codice)', 'Il codice IMO deve essere univoco.')
