from odoo import fields, models


class Ports(models.Model):
    _name = 'codestorm.ports'
    _description = 'Porto'
    _order = 'name'

    name = fields.Char('Nome', required=True)
    codice = fields.Char('Codice UN/LOCODE', copy=False)
    citta = fields.Char('Città')
    country_id = fields.Many2one('res.country', 'Nazione')
    note = fields.Text('Note')
    active = fields.Boolean(default=True)

    _codice_unique = models.Constraint(
        'UNIQUE(codice)', 'Il codice del porto deve essere univoco.')
