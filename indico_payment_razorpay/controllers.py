# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2021 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

import json
import time
from urllib.parse import urljoin
from flask_pluginengine import render_plugin_template
import requests
from flask import flash, redirect, request
from requests import RequestException
from werkzeug.exceptions import BadRequest, NotFound

from indico.core.plugins import url_for_plugin
from indico.modules.events.payment.controllers import RHPaymentBase
from indico.modules.events.payment.models.transactions import TransactionAction
from indico.modules.events.payment.notifications import notify_amount_inconsistency
from indico.modules.events.payment.util import get_active_payment_plugins, register_transaction
from indico.modules.events.registration.models.registrations import Registration
from indico.web.flask.util import url_for
from indico.web.rh import RH

from indico_payment_razorpay import _
from indico_payment_razorpay.plugin import RazorpayPaymentPlugin
import razorpay
from razorpay.errors import SignatureVerificationError
from indico_payment_razorpay.util import PROVIDER_RAZORPAY, to_large_currency, to_small_currency

class TransactionFailure(Exception):
    """A transaction with Razorpay failed.

    :param step: name of the step at which the transaction failed
    :param details: verbose description of what went wrong
    """

    def __init__(self, step, details=None):
        self.step = step
        self.details = details


class RHRazorpayBase(RH):
    """Request Handler for asynchronous callbacks from Razorpay.

    These handlers are used either by

    - the user, when he is redirected from Razorpay back to Indico
    - Razorpay, when it sends back the result of a transaction
    """

    CSRF_ENABLED = False

    def _process_args(self):
        credentials = (RazorpayPaymentPlugin.settings.get('username'), RazorpayPaymentPlugin.settings.get('password'))
        client = razorpay.Client(auth=credentials)
        self.client = client
        self.registration = Registration.query.filter_by(uuid=request.args['token']).first()
        if not self.registration:
            raise BadRequest
        self.order = self.registration.transaction.data['order']


class RHInitRazorpayPayment(RHPaymentBase):
    def _get_transaction_parameters(self):
        """Get parameters for creating a transaction request."""
        settings = RazorpayPaymentPlugin.settings.get_all()
        format_map = {
            'user_id': self.registration.user_id,
            'user_name': self.registration.full_name,
            'user_firstname': self.registration.first_name,
            'user_lastname': self.registration.last_name,
            'event_id': self.registration.event_id,
            'event_title': self.registration.event.title,
            'registration_id': self.registration.id,
            'regform_title': self.registration.registration_form.title,
            'user_email': self.registration.email,
            'currency': self.registration.currency,
            'org_name': settings['org_name'],
            'url':url_for_plugin('payment_razorpay.capture',self.registration.locator.uuid, _external=True),
            'transaction':self.registration.transaction,
        }
        order_description = settings['order_description'].format(**format_map)
        order_identifier = settings['order_identifier'].format(**format_map)
        markup = settings['markup']
        marked_up_amount = self.registration.price
        marked_up_amount += (self.registration.price * markup) / 100000
        transaction_parameters = {k:v for k,v in format_map.items()}
        transaction_parameters['order_description'] = order_description
        transaction_parameters['order_identifier'] = order_identifier
        transaction_parameters['amount'] = self.registration.price
        transaction_parameters['rzp_amount'] = marked_up_amount
        transaction_parameters['rzp_int_amount'] = to_small_currency(marked_up_amount,  self.registration.currency)
        transaction_parameters['rzp_api_id'] = settings['username']
        #'NotifyUrl': url_for_plugin('payment_razorpay.notify', self.registration.locator.uuid, _external=True)
        return transaction_parameters

    def _init_payment_page(self, transaction_data):
        """Initialize payment page."""
        payload = {
            "amount":transaction_data['rzp_int_amount'],
            "currency":self.registration.currency,
            "notes":{'order_identifier':transaction_data['order_identifier']
            }
        }
        try:
            resp = self.client.order.create(data=payload)
        except RequestException as exc:
            RazorpayPaymentPlugin.logger.error('Could not initialize payment: %s', exc.response.text)
            raise Exception('Could not initialize payment')
        return resp

    def _process_args(self):
        RHPaymentBase._process_args(self)
        credentials = (RazorpayPaymentPlugin.settings.get('username'), RazorpayPaymentPlugin.settings.get('password'))
        self.client = razorpay.Client(auth=credentials)
        if 'razorpay' not in get_active_payment_plugins(self.event):
            raise NotFound
        if not RazorpayPaymentPlugin.instance.supports_currency(self.registration.currency):
            raise BadRequest

    def _process(self):
        transaction_params = self._get_transaction_parameters()
        rzp_order = self._init_payment_page(transaction_params)

        # create an order
        new_indico_txn = register_transaction(
            self.registration,
            self.registration.price,
            self.registration.currency,
            TransactionAction.pending,
            PROVIDER_RAZORPAY,
            {'order': rzp_order,
             'rzp_int_amount':transaction_params['rzp_int_amount']}
        )
        transaction_params['order_id'] = rzp_order['id']
        if not new_indico_txn:
            # set it on the current transaction if we could not create a next one
            # this happens if we already have a pending transaction and it's incredibly
            # ugly...
            self.registration.transaction.data = {'order': rzp_order,
             'rzp_int_amount':transaction_params['rzp_int_amount']}
        return  render_plugin_template('checkout.html',**transaction_params)


class RHCaptureRazorpayPayment(RHRazorpayBase):
    """Handler for notification from Razorpay service."""

    def _process(self):
        """Process the reply from Razorpay about the transaction."""

        self._process_args()
        self._process_confirmation()
        return redirect(url_for('event_registration.display_regform', self.registration.locator.uuid, _external=True))

    def _process_confirmation(self):
        """Process the confirmation response inside indico."""
        # assert transaction status from Razorpay
        try:
            self._verify_payment()
            if self._is_duplicate_transaction():
                # we have already handled the transaction
                return redirect(url_for('event_registration.display_regform', self.registration.locator.registrant))
            if not self._is_authorized():
                RazorpayPaymentPlugin.logger.info('Razorpay Transaction not Authorized yet')
                raise TransactionFailure(step='Authorization')
            else:
                self._capture_transaction()
                self._register_payment()
        except TransactionFailure as exc:
            RazorpayPaymentPlugin.logger.warning('Razorpay transaction failed during %s: %s', exc.step, exc.details)
            register_transaction(
                self.registration,
                self.registration.transaction.amount,
                self.registration.transaction.currency,
                # XXX: this is indeed reject and not cancel (cancel is "mark as unpaid" and
                # only used for manual transactions)
                TransactionAction.reject,
                provider=PROVIDER_RAZORPAY,
            data={'order': self.order,
                  'rzp_int_amount':self.registration.transaction.data['rzp_int_amount'],}
            )
            flash(_('Yout payment has failed .'), 'info')
            return
        RazorpayPaymentPlugin.logger.info("{} completed, redirecting user now".format(self.order['id']))
        flash(_('Yout payment was successful.'), 'info')
        return

    def _is_authorized(self):
        payment_id = self.rzp_payment['razorpay_payment_id']
        order_obj = self.client.payment.fetch(payment_id)
        if order_obj['status'] != 'authorized':
            raise TransactionFailure('authorization')
        return True

    def _verify_payment(self):

        payload = {}
        payload['razorpay_order_id'] = self.order['id']
        payload['razorpay_payment_id'] = request.form.get('razorpay_payment_id')
        payload['razorpay_signature'] = request.form.get('razorpay_signature')
        RazorpayPaymentPlugin.logger.warn('Razorpay Transaction Post Received {}',format(str(payload)))
        self.rzp_payment = payload
        try:
            self.client.utility.verify_payment_signature(payload)
        except SignatureVerificationError as exc:
            raise TransactionFailure('Verification')
        return True

    def _is_duplicate_transaction(self):
        """Check if this transaction has already been recorded."""
        prev_transaction = self.registration.transaction
        if (
            not prev_transaction or
            prev_transaction.provider != PROVIDER_RAZORPAY or
            'Transaction' not in prev_transaction.data
        ):
            return False
        old = prev_transaction.data['Transaction']
        new = self.rzp_payment
        return old['razorpay_payment_id'] == new['razorpay_payment_id']

    def _capture_transaction(self):
        """Confirm to Razorpay that the transaction is accepted.

        On success returns the response JSON data.
        """
        payment_id = self.rzp_payment['razorpay_payment_id']
        payment_amount = self.registration.transaction.data['rzp_int_amount']
        resp = self.client.payment.capture(payment_id, payment_amount, {"currency":self.registration.transaction.currency})
        RazorpayPaymentPlugin.logger.info(str(resp))
        if 'error' in resp:
            raise TransactionFailure(step='capture')
        RazorpayPaymentPlugin.logger.info("Payment ID {} Captured".format(payment_id))
        return

    def _register_payment(self):
        """Register the transaction as paid."""
        register_transaction(
            self.registration,
            self.registration.transaction.amount,
            self.registration.transaction.currency,
            TransactionAction.complete,
            PROVIDER_RAZORPAY,
            data={'order': self.order,
                  'rzp_int_amount':self.registration.transaction.data['rzp_int_amount'],
                  'Transaction':self.rzp_payment}
        )
        RazorpayPaymentPlugin.logger.info("{} registered".format(self.order['id']))
