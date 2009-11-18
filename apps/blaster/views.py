from datetime import datetime

from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db import transaction

from blaster.models import *
from schools.models import Headmaster, School

from rapidsms.webui.utils import render_to_response

def index(req, template_name="blaster/index.html"):
    all_blasts = MessageBlast.objects.order_by("-date")
    return render_to_response(req, template_name, {"blasts": all_blasts})

def single_blast(req, id, template_name="blaster/single.html"):
    blast = MessageBlast.objects.get(id=id)
    return render_to_response(req, template_name, {"blast": blast})
    
def new(req, template_name="blaster/new.html"):
    def get(req, template_name="blaster/new.html"):
        messages = BlastableMessage.objects.all()
        # TODO: genericize this out to only depend on reporters
        reporters = Headmaster.objects.all()    
        return render_to_response(req, template_name, {"messages": messages,
                                                       "reporters": reporters
                                                       } )    
    
    @transaction.commit_manually
    def post(req):
        print req.POST
        message = req.POST["message"]
        errors = []
        if not message:
            errors.append("You must select a message!")
        elif message == "new":
            if not req.POST["new_question"]:
                errors.append("You must fill in the new question text!")
            else:
                question = BlastableMessage.objects.create(text=req.POST["new_question"])
                question.save()
        else:
            question = BlastableMessage.objects.get(id=int(message))

        if "select_reporter" not in req.POST or not req.POST["select_reporter"]:
            errors.append("You must select at least one person to send to!")
        if errors:
            transaction.rollback()
            messages = BlastableMessage.objects.all()
            # TODO: genericize this out to only depend on reporters
            reporters = Headmaster.objects.all()    
            return render_to_response(req, template_name,{"messages": messages,
                                                          "reporters": reporters,
                                                          "errors": "<br>".join(errors)
                                                          } )
        # no errors
        reporter_ids = req.POST.getlist("select_reporter")
        print reporter_ids
        now = datetime.now()
        blast = MessageBlast.objects.create(message=question,date=now)
        for id in reporter_ids:
            reporter = Reporter.objects.get(id=id)
            instance = BlastedMessage.objects.create(blast=blast, reporter=reporter)
        transaction.commit()
        return HttpResponse("thanks!")
    
    # invoke the correct function...
    # this should be abstracted away
    if   req.method == "GET":  return get(req, template_name)
    elif req.method == "POST": return post(req)

    