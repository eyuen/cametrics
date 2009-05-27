import os, logging

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from myapp.models import Storage, Statistics
import util, myapp.renderer

 
class MainPage(webapp.RequestHandler):
  def get(self, key, namespace, format):
    logging.warning("%s, %s, %s" % (key, namespace, format))
    
    format = format or self.request.GET.get('format', 'json')
    ns, data_path = util.getParts(ns)
    data = Storage.all().filter('campaign = ', campaign).filter('namespace = ', ns).fetch(1000) # todo, paginator
    stats = Statistics.get_by_campaign_and_namespace(campaign, ns)
    return renderer.get(format)(request, format, data, stats, data_path)
    
  def post(self, key, namespace, format):
    pass
    

'''
def measurements(request, key, path, format):
  logging.debug('measurements::path = %s' % path)
  logging.debug('measurements::format = %s' % format)
  if (not key):
    return HttpResponse('Invalid service usage')
  
  campaign = Campaign.get(key)
  if (not campaign):
    return HttpResponse('Campaign not found')
  
  ns = (path or '').strip('/').replace('/', '.')
  
  if request.method == 'GET':
    format = format or self.request.GET.get('format', 'json')
    ns, data_path = util.getParts(ns)
    data = Storage.all().filter('campaign = ', campaign).filter('namespace = ', ns).fetch(1000) # todo, paginator
    stats = Statistics.get_by_campaign_and_namespace(campaign, ns)
    return renderer.get(format)(request, format, data, stats, data_path)
  
  elif request.method == 'POST':
    if 'bulk' in request.POST.get('type'):
      data = simplejson.loads(request.POST.get('data') or '[]')
      saved = False
      for datum in data:
        if create_datum(campaign, datum.get('namespace'), datum):
          saved = True
    else:
      saved = create_datum(campaign, ns, request.POST)
    return HttpResponse(status = (saved and 201 or 304))
      
  elif request.method == 'DELETE':
    return HttpResponse('Not yet supported, please contact admin.', status = 304)

  return HttpResponse('Internal Error', status = 500)

def create_datum(campaign, ns, obj = {}):
  value = obj.get('value')
  kind = obj.get('type', 'number')
  logging.debug('POST | value: %s | kind: %s' % (value, kind))
  
  datum = Storage(campaign = campaign, namespace = ns, type = kind, value = value)
  saved = bool(datum.put())
  if not saved:
    logging.critical('Could not save: Storage(%s, %s, %s, %s)' % (campaign, ns, value, kind))
  return saved

'''
    
application = webapp.WSGIApplication(debug = os.environ['SERVER_SOFTWARE'].startswith('Dev'), url_mapping = [
  ('/measure/([^/]+)/([^\.]+)?(?:\.(.+))?', MainPage)
])
 
if __name__ == "__main__":  
  run_wsgi_app(application)