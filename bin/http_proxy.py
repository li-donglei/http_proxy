#coding:utf-8

import logging
logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s [line:%(lineno)d] %(levelname)s %(message)s',
                #format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%H:%M:%S',
                #datefmt='%a, %d %b %Y %H:%M:%S',
                #filename='myapp.log',
                #filemode='w'
                )

import sys, os
#from gevent import monkey; monkey.patch_socket()
from gevent import socket
from gevent.server import StreamServer
#from gevent.pool import Pool as gPool
from multiprocessing import cpu_count
#import socket


#import count

def parser_response_header(response_header):
    '''解析http响应报文头'''
    Transfer_Encoding = False
    Content_Length = 0
    status_code = 0
    lines = response_header.strip().split('\r\n')
    status_code = int(lines[0].split(' ')[1])
    
    headers = {}
    for i in range(1,len(lines)):
        line= lines[i].split(':')
        key = line.pop(0)
        value = ''.join(line)
        headers[key] = value.strip()
    #logging.debug(str(headers))
    
    return status_code, headers


def parser_request_headers(request_headers):
    '''解析http请求头,返回（host, port, method, uri, headers）'''
    lines = request_headers.strip().split('\r\n')
    try:
        '''解析请求方法和uri'''
        line0 = lines[0].split(' ')
        method = line0[0].upper()
        uri = line0[1]
        #logging.debug(str(line0))
    
        '''解析其他header'''
        headers = {}
        for i in range(1,len(lines)):
            line= lines[i].split(':')
            key = line.pop(0)
            value = ''.join(line)
            headers[key] = value.strip()
        #logging.debug(str(headers))

        '''处理目标主机和端口'''
        target_host_and_port = headers['Host'].split(':')
        if len(target_host_and_port)==1:
            target_host = target_host_and_port[0]
            target_port = 80
        else:
            target_host = target_host_and_port[0]
            target_port = int(target_host_and_port[1].strip())
    except Exception, e: 
        logging.warning(str(type(e))+' '+str(e)+' err')
        return None,None,None,None,None
    return target_host, target_port, method, uri, headers
    
    
def do_proxy(host, port, method, uri, request_headers, request, ss):
    '''获取目标主机的http应答, 并转发应答包'''      
    c = socket.socket()
    try:
        c.connect((host, port))
    except Exception, e:
        logging.warning(str(type(e))+' '+str(e)+' err')
        c.close()
        ss.send(str(type(e))+' '+str(e)+' err')
        ss.close()
        return
    try:   
        c.send(request)
        response = ''
        got_header = False
        headers = {}
        while 1:
            buf = c.recv(4096)
            response = response + buf
            ss.send(buf)
            if not got_header and '\r\n\r\n' in response:
                got_header = True
                response_header = response.split('\r\n\r\n')[0] + '\r\n\r\n'
                logging.debug(response_header)
                header_length = len(response_header)
                status_code, headers = parser_response_header(response_header)
                #logging.debug(str(status_code))

            if got_header:
                '''没有内容，直接返回报文头就行'''
                if method in ['HEAD']:
                    break
                if method in ['GET', 'POST']:
                    if status_code in [204,301,302,303,304,307]:
                        break
                    '''正常的判断是否接收完响应的方式'''
                    if 'Transfer-Encoding' in headers:
                        if not buf:
                            logging.debug('not buf in tranfer-encoding')
                            break 
                    if 'Content-Length' in headers:
                        if int(headers['Content-Length']) <= len(response)-header_length:
                            break
                    if not 'Content-Length' in headers and not 'Transfer-Encoding' in headers and not buf:
                        logging.debug('not buf')
                        break 
            if not buf:
                logging.error('response not buf')
                break
        #logging.info(str(status_code)+' response len'+str(len(response)-header_length)+uri[:0])
    except Exception, e:
        logging.warning(str(type(e))+' '+str(e)+' err')
        c.close()
        ss.close()
        return
    c.close()
    ss.close()

def proxyer(ss, add):
    #logging.debug(ss)
    '''接收http请求'''
    request = ''
    got_header = False
    headers = {}
    while 1:
        buf = ss.recv(4096)
        request = request + buf
        if not got_header and '\r\n\r\n' in request:
            got_header = True
            request_header = request.split('\r\n\r\n')[0] + '\r\n\r\n'
            header_length = len(request_header)
            host, port, method, uri, headers = parser_request_headers(request_header)
            if not host or not port or not method in ['HEAD','GET','POST']:
                logging.warning('parser request err or method not support ,close this task')
                ss.close()
                return
            if method in ['GET','HEAD']:
                break
        if got_header and method in ['POST']:
            if 'Content-Length' in headers:
                if int(headers['Content-Length']) <= len(request)-header_length:
                    break
            else:
                logging.warning('no Content-Length in POST request,close this task')
                ss.close()
                return
        if not buf:
            break
    if not '\r\n\r\n' in request:
        logging.warning('request err,len = '+str(len(request))+',close this task')
        ss.close()
        return
    #logging.debug('request length: '+str(len(request)))
    logging.debug('\n'+request)
    #logging.info(host+':'+str(port)+' '+method+' '+uri[:0])
    
    '''获取目标主机的http应答, 并转发应答包'''
    #count.dic[os.getpid()] = count.dic.get(os.getpid(),0) + 1
    #print count.dic,uri
    do_proxy(host, port, method, uri, headers, request, ss)
    #count.dic[os.getpid()] = count.dic[os.getpid()] - 1
    #print count.dic
    
if __name__ == '__main__':
    #gpool = gPool(128)
    server = StreamServer(('', int(sys.argv[1])), proxyer)#, spawn=gpool)    
    if cpu_count()>1: server.max_accept  = 1
    server.start() 
    pid_list = []
    for i in range(cpu_count()):
        pid = os.fork()
        if pid == 0: 
            del pid_list
            server.serve_forever() 
        else:
            pid_list.append(str(pid))
    with open(sys.path[0]+'/pid','w') as f:
        f.write('|'.join(pid_list))
    print('start processes: '+'|'.join(pid_list)+' ok')
        