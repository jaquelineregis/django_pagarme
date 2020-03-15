from collections import ChainMap

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.csrf import csrf_exempt

from django_pagarme import facade
from django_pagarme.facade import InvalidNotificationStatusTransition
from django_pagarme.models import PaymentViolation


def contact_info(request, slug):
    if request.method == 'GET':
        form = facade.ContactForm()
        ctx = {'contact_form': form, 'slug': slug}
        return render(request, 'django_pagarme/contact_form.html', ctx)

    dct = {key: request.POST[key] for key in 'name phone email'.split()}
    dct['payment_item_slug'] = slug
    try:
        dct = facade.validate_and_inform_contact_info(**dct)
    except facade.InvalidContactData as e:
        ctx = {'contact_form': e.contact_form, 'slug': slug}
        resp = render(request, 'django_pagarme/contact_form_errors.html', ctx, status=400)
        return resp
    else:
        path = reverse('django_pagarme:pagarme', kwargs={'slug': slug})
        dct['open_modal'] = 'true'
        query_string = urlencode(dct)
        return redirect(f'{path}?{query_string}')


def capture(request):
    token = request.POST['token']
    try:
        payment = facade.capture(token, request.user.id)
    except facade.PaymentViolation as violation:
        return JsonResponse({'errors': str(violation)}, status=400)
    else:
        return JsonResponse(payment.to_dict())


@csrf_exempt
def notification(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed([request.method])

    raw_body = request.body.decode('utf8')
    expected_signature = request.headers.get('X-Hub-Signature', '')
    transaction_id = request.POST['transaction[id]']
    current_status = request.POST['current_status']
    try:
        facade.handle_notification(transaction_id, current_status, raw_body, expected_signature)
    except PaymentViolation:
        return HttpResponseBadRequest()
    except InvalidNotificationStatusTransition:
        pass

    return HttpResponse()


def pagarme(request, slug: str):
    open_modal = request.GET.get('open_modal', '').lower() == 'true'
    customer_qs_data = {k: request.GET.get(k, '') for k in ['name', 'email', 'phone']}
    customer_qs_data = {k: v for k, v in customer_qs_data.items() if v}
    user = request.user
    if user.is_authenticated:
        user_data = {'external_id': user.id, 'name': user.first_name, 'email': user.email}
        customer = ChainMap(customer_qs_data, user_data)
    else:
        customer = customer_qs_data
    ctx = {
        'payment_item': facade.get_payment_item(slug),
        'open_modal': open_modal,
        'customer': customer,
        'slug': slug
    }
    return render(request, 'django_pagarme/pagarme.html', ctx)
