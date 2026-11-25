from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CruisesStops(models.Model):
    _name = 'codestorm.cruises.stops'
    _description = 'Tappa crociera'
    _order = 'cruise_id, sequence, data_arrivo'

    sequence = fields.Integer(default=10)
    cruise_id = fields.Many2one(
        'codestorm.cruises', 'Crociera', required=True, ondelete='cascade', index=True)
    port_id = fields.Many2one(
        'codestorm.ports', 'Porto', required=True, ondelete='restrict')
    data_arrivo = fields.Datetime('Arrivo')
    data_partenza = fields.Datetime('Partenza')
    note = fields.Text('Note')

    @api.constrains('data_arrivo', 'data_partenza')
    def _check_date(self):
        for rec in self:
            if rec.data_arrivo and rec.data_partenza and rec.data_partenza < rec.data_arrivo:
                raise ValidationError('La partenza non può precedere l\'arrivo.')
