import os, logging, math, re, urlparse
from django.utils import simplejson

from models import Storage, Statistics, Histogram
import util, visualize

DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Dev')

def get(prop):
  glbs = globals()
  Renderers = map(lambda p: glbs[p], [p for p in glbs if '__' not in p and p is not 'get'])
  for Class in Renderers:
    if hasattr(Class, 'match_formats') and Class.match_formats and prop in Class.match_formats:
      return Class

  logging.debug('No Renderer for %s' % prop)
  return Renderer

MIMETYPES = {
  'json': DEBUG and 'text/html' or 'application/json',
  'html': 'text/html',
  'csv': 'text/csv',
  'plain': 'text/plain',
  'javascript': 'text/javascript',
}

class NoRenderer(object):  
  @classmethod
  def get_values(cls, campaign, ns, path):
    return []
  
  @classmethod
  def get_statistics(cls, campaign, ns, path):
    return {}
    
  @classmethod
  def render_values(cls, page, path):
    data = cls.get_values(page.campaign, page.namespace, path)
    return cls.render(page, data)
      
  @classmethod
  def render_stats(cls, page, path):
    stats = cls.get_statistics(page.campaign, page.namespace, path)
    return cls.render(page, stats)
  
  @classmethod
  def render(cls, page, data = None):
    page.response.headers.add_header('Content-Type', MIMETYPES.get(page.format, 'text/plain'))
    page.response.out.write(data)
    page.response.set_status(data and 200 or 204)

class Renderer(NoRenderer):  
  @classmethod
  def get_values(cls, campaign, ns, path):
    query = Storage.all().filter('campaign = ', campaign).filter('namespace = ', ns)
    return [datum for datum in query] # todo, paginator/generator
  
  @classmethod
  def get_statistics(cls, campaign, ns, path):
    data = Statistics.get_by_campaign_and_namespace(campaign, ns)
    if (data and path):
      path = path.lstrip('stats').strip('.')
      if path:
        data = util.getattr_by_path(data, path)
    return data

class JSONRenderer(Renderer):
  match_formats = ['json']
  
  @classmethod
  def get_values(cls, campaign, ns, path):
    data = super(JSONRenderer, cls).get_values(campaign, ns, path)
    return map(lambda d: util.replace_datastore_types(d.to_dict()), data)
  
  @classmethod
  def get_statistics(cls, campaign, ns, path):
    data = super(JSONRenderer, cls).get_statistics(campaign, ns, path)
    if isinstance(data, (Histogram, Statistics)):
        data = util.replace_datastore_types(data.to_dict())
    return data
    
  @classmethod
  def render(cls, page, data = None):
    data = data or {
      'values': cls.get_values(page.campaign, page.namespace, ''),
      'stats': cls.get_statistics(page.campaign, page.namespace, '')
    }
    return super(JSONRenderer, cls).render(page, simplejson.dumps(data))
    
class GChartRenderer(Renderer):
  match_formats = ['gc', 'gchart']

  @classmethod
  def get_values(cls, campaign, ns, path):
    data = super(GChartRenderer, cls).get_values(campaign, ns, path)
    return map(lambda d: hasattr(d, 'value') and d.value or None, data)  
  
  @classmethod
  def get_statistics(cls, campaign, ns, path):
    data = super(GChartRenderer, cls).get_statistics(campaign, ns, path)
    if isinstance(data, Histogram):
        data = data.to_dict()
    return data
      
  @classmethod
  def render(cls, page, data = None):
    if not data:
      return NoRenderer.render(page)
    
    stats = Statistics.get_by_campaign_and_namespace(page.campaign, page.namespace) # todo, how to clean the type assoc to the campaign/namespace
    logging.info('Getting visualization for: %s' % stats.type)
    url = visualize.get(stats.type).get_url(page.request, data)
    logging.info('Redirecting to: %s' % url)
    if url:
      if DEBUG:
        return page.response.out.write('<img src="%s" />' % url)
      return page.redirect(url)
    page.response.set_status(500)
  
class GMapRenderer(Renderer):
  ''' Google Map API Renderer
  
  Transforms a longitude/latitude object (filtered, if either are not present) into three variations (using the `type` request argument):
    encoded - (default) An Encoded String as described in: http://code.google.com/apis/maps/documentation/polylinealgorithm.html
    polyline - A JavaScript polyline as described in this example: http://code.google.com/apis/maps/documentation/overlays.html#Encoded_Polylines, requires a callback or class parameter (see below)
    raw - A JSON object
    
  Other Query Arguments:
    callback - Name of the JavaScript function to call with the first argument the object returned
    class - Name of the GMap class to addOverlay with default options or user overriden options
    ... - Any other option available to the GPolyline.fromEncoded object options, the parameter is the object key. For example color=#FF0000 (only appropriate for when you pass the class parameter)
  '''
  match_formats = ['gm', 'gmap']
  
  options = {
    'color': '#FF0000',
    'weight': 2,
    'zoomFactor': 32,
    'numLevels': 4  
  }
  
  @classmethod
  def render_values(cls, page, path):
    gmtype = page.request.get('type', 'raw')
    if gmtype == 'raw':
      return JSONRenderer.render_values(page, path)
    data = cls.get_values(page.campaign, page.namespace, path)
    options = GMapRenderer.encode(data)
    callback = page.request.get('callback', '')  
    if gmtype == 'polyline':
      options.update(cls.options)
      callback = callback or '%s.addOverlay' % (page.request.get('class') or 'map')
      
      get = page.request.GET.copy()
      try: # todo, refactor
        del get['callback']
        del get['type']
        del get['class']
      except:
        pass
      options.update(get)
      
    options = simplejson.dumps(options)
    if gmtype == 'polyline':
      data = '%s(new GPolyline.fromEncoded(%s));' % (callback, options)
    elif callback:
      data = '%s(%s);' % (callback, options)
    else:
      data = '%s' % options    
    return cls.render(page, data)
                
  @staticmethod
  def encode(points):
    """ Encode a coordinates into an encoded string.
    
    For more information: http://wiki.urban.cens.ucla.edu/index.php/How-to_use_Google_Maps_polyline_encoding_to_compact_data_size
    
    Author
      Jason Ryder, <ryder.jason@gmail.com>
    """
    plat = 0
    plng = 0
    encoded_points = ''
    encoded_levels = ''
    for i, point in enumerate(points):
      try:
        if isinstance(point, dict):
          lat = point.get('latitude')
          lng = point.get('longitude')
        else:
          lat = point.latitude
          lng = point.longitude
      except:
        continue
        
      level = 3 - i % 4                    
      
      late5 = int(math.floor(lat * 1e5))
      lnge5 = int(math.floor(lng * 1e5)) 
      
      dlat = late5 - plat
      dlng = lnge5 - plng                
      
      plat = late5
      plng = lnge5                       
      
      encoded_points += GMapRenderer.encodeSignedNumber(dlat) + GMapRenderer.encodeSignedNumber(dlng)
      encoded_levels += GMapRenderer.encodeNumber(level) 
    
    return {
      'points': encoded_points,
      'levels': encoded_levels
    }
    
  @staticmethod
  def encodeNumber(num):
    '''Encode an unsigned number in the encode format.
    '''
    encodeString = ""
    while num >= 0x20:
      encodeString += chr((0x20 | (num & 0x1f)) + 63)
      num >>= 5
    encodeString += chr(num + 63)
    return encodeString
    
  @staticmethod
  def encodeSignedNumber(num):
    '''Encode a signed number into the google maps polyline encode format.
    '''
    sgn_num = num << 1
    if num < 0:
      sgn_num = ~(sgn_num)
    return GMapRenderer.encodeNumber(sgn_num)