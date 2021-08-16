# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2021 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

from indico.core.plugins import IndicoPluginBlueprint

from indico_payment_razorpay.controllers import (RHInitRazorpayPayment, RHCaptureRazorpayPayment)


blueprint = IndicoPluginBlueprint(
    'payment_razorpay', __name__,
    url_prefix='/event/<int:event_id>/registrations/<int:reg_form_id>/payment/razorpay'
)

blueprint.add_url_rule('/init', 'init', RHInitRazorpayPayment, methods=['GET'])
blueprint.add_url_rule('/capture', 'capture', RHCaptureRazorpayPayment, methods=['POST'])
