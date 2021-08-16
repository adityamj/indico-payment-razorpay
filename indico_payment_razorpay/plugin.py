# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2021 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

from indico.core.plugins import IndicoPlugin
from indico.modules.events.payment import PaymentPluginMixin

from indico_payment_razorpay.forms import PluginSettingsForm, EventSettingsForm


class RazorpayPaymentPlugin(PaymentPluginMixin, IndicoPlugin):
    """Razorpay

    Provides a payment method using the Razorpay API.
    """

    configurable = True
    #: form for default configuration across events
    settings_form = PluginSettingsForm
    #: form for configuration for specific events
    #: global default settings - should be a reasonable default

    event_settings_form = EventSettingsForm
    default_settings = {
        'method_name': 'Razorpay',
        'org_name': None,
        'markup': 2417,
        'username': None,
        'password': None,
        'order_description': '{event_title}, {regform_title}, {user_name}',
        'order_identifier': 'e{event_id}r{registration_id}',
        'notification_mail': None
    }
    default_event_settings = {
        'enabled': True,
        'method_name': None,
        'order_description': None,
        'order_identifier': None,
        'notification_mail': None,
    }
    def get_blueprints(self):
        """Blueprint for URL endpoints with callbacks."""
        from indico_payment_razorpay.blueprint import blueprint
        return blueprint
