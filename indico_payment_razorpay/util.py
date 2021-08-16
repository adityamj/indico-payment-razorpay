# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2021 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

import uuid

import iso4217
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented

from indico_payment_razorpay import _

# payment provider identifier
PROVIDER_RAZORPAY = 'razorpay'

# currencies for which the major to minor currency ratio
# is not a multiple of 10
ACCEPTED_CURRENCY  = {'INR'}


def validate_currency(iso_code):
    """Check whether the currency can be properly handled by this plugin.

    :param iso_code: an ISO4217 currency code, e.g. ``"EUR"``
    :raises: :py:exc:`~.HTTPNotImplemented` if the currency is not valid
    """
    if iso_code not in ACCEPTED_CURRENCY:
        raise HTTPNotImplemented(
            _("Unsupported currency '{}' for Razorpay. Please contact the organizers").format(iso_code)
        )


def to_small_currency(large_currency_amount, iso_code):
    """Convert an amount from large currency to small currency.

    :param large_currency_amount: the amount in large currency, e.g. ``2.3``
    :param iso_code: the ISO currency code, e.g. ``"EUR"``
    :return: the amount in small currency, e.g. ``230``
    """
    validate_currency(iso_code)
    exponent = iso4217.Currency(iso_code).exponent
    if exponent == 0:
        return large_currency_amount
    return int(large_currency_amount * (10 ** exponent))


def to_large_currency(small_currency_amount, iso_code):
    """Inverse of :py:func:`to_small_currency`."""
    validate_currency(iso_code)
    exponent = iso4217.Currency(iso_code).exponent
    if exponent == 0:
        return small_currency_amount
    return small_currency_amount / (10 ** exponent)
