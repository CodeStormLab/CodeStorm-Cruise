from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Cruises(models.Model):
    _name = 'codestorm.cruises'
    _description = 'Cruise'
    _order = 'data_inizio desc, name'

    name = fields.Char('Nome', required=True)
    codice = fields.Char('Codice', copy=False)
    cliente_id = fields.Many2one('res.partner', 'Cliente')
    ship_id = fields.Many2one('codestorm.ships', 'Nave', ondelete='restrict')
    stop_ids = fields.One2many('codestorm.cruises.stops', 'cruise_id', 'Tappe')
    responsabile_id = fields.Many2one(
        'res.users', 'Responsabile', default=lambda self: self.env.user)
    data_inizio = fields.Date('Data inizio', default=fields.Date.context_today)
    data_fine = fields.Date('Data fine')
    stato = fields.Selection([
        ('bozza', 'Bozza'),
        ('in_corso', 'In corso'),
        ('chiuso', 'Chiuso'),
    ], default='bozza', required=True)
    budget = fields.Float('Budget')
    note = fields.Text('Note')
    # Il nome deve contenere "image": base_import scarica automaticamente gli URL
    # http(s) solo per i campi binari con attachment il cui nome contiene
    # image/icon/logo/picture. In alternativa accetta il contenuto in base64.
    image = fields.Image('Immagine', max_width=1920, max_height=1920)
    active = fields.Boolean(default=True)

    durata_giorni = fields.Integer(
        'Durata (giorni)', compute='_compute_durata', store=True)

    _codice_unique = models.Constraint(
        'UNIQUE(codice)', 'Il codice deve essere univoco.')

    @api.depends('data_inizio', 'data_fine')
    def _compute_durata(self):
        for rec in self:
            if rec.data_inizio and rec.data_fine:
                rec.durata_giorni = (rec.data_fine - rec.data_inizio).days
            else:
                rec.durata_giorni = 0

    @api.constrains('data_inizio', 'data_fine')
    def _check_date(self):
        for rec in self:
            if rec.data_inizio and rec.data_fine and rec.data_fine < rec.data_inizio:
                raise ValidationError('La data di fine non può precedere quella di inizio.')
