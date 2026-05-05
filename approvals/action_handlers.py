from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect

from approvals.models import ApprovalTask


def handle_task_action(
    request,
    *,
    request_obj_queryset,
    request_pk,
    task_id,
    success_message,
    detail_route_name,
    action,
    comment=None,
    request_fk_name=None,
    use_generic_request_object=False,
):
    request_obj = get_object_or_404(request_obj_queryset, pk=request_pk)

    task_lookup = {"pk": task_id}

    if use_generic_request_object:
        task_lookup["request_content_type"] = ContentType.objects.get_for_model(request_obj.__class__)
        task_lookup["request_object_id"] = request_obj.pk
    elif request_fk_name:
        task_lookup[request_fk_name] = request_obj
    else:
        raise ValueError("Either request_fk_name or use_generic_request_object=True is required.")

    task = get_object_or_404(ApprovalTask, **task_lookup)

    try:
        if comment is None:
            action(task, request.user)
        else:
            action(task, request.user, comment)
        messages.success(request, success_message.format(step_name=task.step_name))
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)

    return redirect(detail_route_name, pk=request_obj.pk)