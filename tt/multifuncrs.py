import numpy as np
from numpy import prod, nonzero, size
import math
import tt
from tt.maxvol import maxvol
import copy

def reshape(a, size):
    return np.reshape(a, size, order='F')


def my_chop2(sv, eps):
    if eps <= 0.0:
        r = len(sv)
        return r
    eos = eps ** 2
    sv0 = np.cumsum(abs(sv[::-1]) ** 2)[::-1]
    ff = [i for i in range(len(sv0)) if sv0[i] < eps ** 2]
    if len(ff) == 0:
        return len(sv)
    else:
        return np.amin(ff)


def multifuncrs(X, funs, eps=1E-6, varargin=[]):
    nswp = 10
    kickrank = 5
    y = None
    verb = 1
    kicktype = 'amr-two'
    pcatype = 'svd'
    rmax = 999999 # TODO: infinity
    d2 = 1
    wasrand = False
    trunctype = 'fro'
    do_qr = False
    
    for i in range(0, len(varargin) - 1, 2):
        tmp = varargin[i].lower()
        arg = varargin[i + 1]
        if tmp == 'nswp':
            nswp      = arg
        elif tmp == 'y0':
            y         = arg
        elif tmp == 'kickrank':
            kickrank  = arg
        elif tmp == 'rmax':
            rmax      = arg
        elif tmp == 'verb':
            verb      = arg
        elif tmp == 'kicktype':
            kicktype  = arg
        elif tmp == 'pcatype':
            pcatype   = arg
        elif tmp == 'trunctype':
            trunctype = arg
        elif tmp == 'd2':
            d2        = arg
        elif tmp == 'qr':
            do_qr     = arg
        else:
            print "Unrecognized option: %s" % tmp
    
    nx = len(X)
    d = X[0].d
    n = X[0].n
    rx = np.transpose(np.array([ttx.r for ttx in X]))
    crx = np.transpose(np.array([tt.tensor.to_list(ttx) for ttx in X], dtype=np.object))
    
    if y is None:
        ry = d2 * np.ones((d + 1,), dtype=np.int32)
        ry[0] = 1
        y = tt.rand(n, d, ry)
        wasrand = True
    
    ry = y.r
    cry = tt.tensor.to_list(y)
    
    Ry = np.zeros((d + 1, ), dtype=np.object)
    Ry[0] = [[1]]
    Ry[d] = [[1]]
    Rx = np.zeros((d+1, nx), dtype=np.object)
    Rx[0, :] = np.ones(nx)
    Rx[d, :] = np.ones(nx)
    
    block_order = [+d, -d]
    
    for i in range(0, d - 1):
        cr = cry[i]
        cr = reshape(cr, (ry[i] * n[i], ry[i + 1]))
        cr, rv = np.linalg.qr(cr)
        cr2 = cry[i + 1]
        cr2 = reshape(cr2, (ry[i + 1], n[i + 1] * ry[i + 2]))
        cr2 = np.dot(rv, cr2) # matrix multiplication
        ry[i + 1] = cr.shape[1]
        cr = reshape(cr, (ry[i], n[i], ry[i + 1]))
        cry[i + 1] = reshape(cr2, (ry[i + 1], n[i + 1], ry[i + 2]))
        cry[i] = cr
        
        Ry[i + 1] = np.dot(Ry[i], reshape(cr, (ry[i], n[i] * ry[i + 1])))
        Ry[i + 1] = reshape(Ry[i + 1], (ry[i] * n[i], ry[i + 1]))
        curind = []
        if wasrand:
            # EVERY DAY I'M SHUFFLIN'
            curind = np.random.permutation(n[i] * ry[i])[:ry[i + 1]]
        else:
            curind = maxvol(Ry[i + 1])
            # curind = maxvol2(Ry[i + 1], 'qr', do_qr) # TODO
        Ry[i + 1] = Ry[i + 1][curind, :]
        for j in range(0, nx):
            Rx[i + 1, j] = reshape(crx[i, j], (rx[i, j], n[i] * rx[i + 1, j]))
            Rx[i + 1, j] = np.dot(Rx[i, j], Rx[i + 1, j])
            Rx[i + 1, j] = reshape(Rx[i + 1, j], (ry[i] * n[i], rx[i + 1, j]))
            Rx[i + 1, j] = Rx[i + 1, j][curind, :]
    
    d2 = ry[d]
    ry[d] = 1
    cry[d - 1] = np.transpose(cry[d - 1], [2, 0, 1]) # permute
    
    last_sweep = False
    swp = 1
    
    dy = np.zeros((d, ))
    max_dy = 0
    
    cur_order = copy.copy(block_order)
    order_index = 1
    i = d - 1
    dirn = int(math.copysign(1, cur_order[order_index])) # can't use 'dir' identifier in python
    
    # DMRG sweeps
    while swp <= nswp or dirn > 0:
        
        oldy = reshape(cry[i], (d2 * ry[i] * n[i] * ry[i + 1],))
        
        if not last_sweep:
            # compute the X superblocks
            curbl = np.zeros((ry[i] * n[i] * ry[i + 1], nx))
            for j in range(0, nx):
                cr = reshape(crx[i, j], (rx[i, j], n[i] * rx[i + 1, j]))
                cr = np.dot(Rx[i, j], cr)
                cr = reshape(cr, (ry[i] * n[i], rx[i + 1, j]))
                cr = np.dot(cr, Rx[i + 1, j])
                curbl[:, j] = cr.flatten('F');
            # call the function
            newy = funs(curbl)
            # multiply with inverted Ry
            newy = reshape(newy, (ry[i], n[i] * ry[i + 1] * d2))
            newy = np.linalg.solve(Ry[i], newy) # y = R \ y
            newy = reshape(newy, (ry[i] * n[i] * ry[i + 1], d2))
            uu, ss, vv = np.linalg.svd(Ry[i+1])
            newy = reshape(np.transpose(newy), (d2 * ry[i] * n[i], ry[i + 1]))
            newy = np.transpose(np.linalg.solve(np.transpose(Ry[i + 1]), np.transpose(newy))) # y=y/R
            newy = reshape(newy, (d2 * ry[i] * n[i] * ry[i + 1],))
        else:
            newy = oldy
        
        dy[i] = np.linalg.norm(newy - oldy) / np.linalg.norm(newy)
        max_dy = max(max_dy, dy[i])
        
        # truncation
        if dirn > 0: # left-to-right
            newy = reshape(newy, (d2, ry[i] * n[i] * ry[i + 1]))
            newy = reshape(np.transpose(newy), (ry[i] * n[i], ry[i + 1] * d2))
        else:
            newy = reshape(newy, (d2 * ry[i], n[i] * ry[i + 1]))
        
        r = 0 # defines a variable in global scope
        
        if kickrank >= 0:
            u, s, v = np.linalg.svd(newy, full_matrices=False)
            v = np.transpose(v)
            if trunctype == "fro" or last_sweep:
                r = my_chop2(s, eps / math.sqrt(d) * np.linalg.norm(s))
            else:
                # truncate taking into account the (r+1) overhead in the cross (T.S.: what?)
                cums = abs(s * np.arange(2, len(s) + 2)) ** 2
                cums = np.cumsum(cums[::-1])[::-1]
                cums = cums / cums[0]
                ff = [i for i in range(len(cums)) if cums[i] < eps ** 2 / d]
                if len(ff) == 0:
                    r = len(s)
                else:
                    r = np.amin(ff)
            r = min(r, rmax, len(s))
        else:
            if dirn > 0:
                u, v = np.linalg.qr(newy)
                v = np.conj(np.transpose(v))
                r = u.shape[1]
                s = np.ones((r, ))
            else:
                v, u = np.linalg.qr(np.transpose(newy))
                v = np.conj(v)
                u = np.conj(np.transpose(u))
                r = u.shape[1]
                s = np.ones((r, ))
        
        if verb > 1:
            print '=multifuncrs=   block %d{%d}, dy: %3.3e, r: %d\n' % (i, dirn, dy[i], r)
        
        # kicks and interfaces
        if dirn > 0 and i < d - 1:
            u = u[:, :r]
            v = np.dot(v[:, :r], np.diag(s[:r]))
            
            # kick
            radd = 0
            rv = 1
            if not last_sweep and kickrank > 0:
                uk = None
                if kicktype == 'amr-two':
                    # AMR(two)-like kick.
                    
                    # compute the X superblocks
                    ind2 = np.unique(np.random.randint(0, ry[i + 2] * n[i + 1], ry[i + 1]))
                    #ind2 = np.unique(np.floor(np.random.rand(ry[i + 1]) * (ry[i + 2] * n[i + 1])))
                    rkick = len(ind2)
                    curbl = np.zeros((ry[i] * n[i] * rkick, nx))
                    for j in range(nx):
                        cr1 = reshape(crx[i, j], (rx[i, j], n[i] * rx[i + 1, j]))
                        cr1 = np.dot(Rx[i, j], cr1)
                        cr1 = reshape(cr1, (ry[i] * n[i], rx[i + 1, j]))
                        cr2 = reshape(crx[i + 1, j], (rx[i + 1, j] * n[i + 1], rx[i + 2, j]))
                        cr2 = np.dot(cr2, Rx[i + 2, j])
                        cr2 = reshape(cr2, (rx[i + 1, j], n[i + 1] * ry[i + 2]))
                        cr2 = cr2[:, ind2]
                        curbl[:, j] = reshape(np.dot(cr1, cr2), (ry[i] * n[i] * rkick,))
                    # call the function
                    uk = funs(curbl)
                    uk = reshape(uk, (ry[i], n[i] * rkick * d2))
                    uk = np.linalg.solve(Ry[i], uk)
                    uk = reshape(uk, (ry[i] * n[i], rkick * d2))
                    if pcatype == 'svd':
                        uk, sk, vk = np.linalg.svd(uk, full_matrices=False)
                        vk = np.transpose(vk)
                        uk = uk[:, :min(kickrank, uk.shape[1])]
                    else:
                        # uk = uchol(np.transpose(uk), kickrank + 1) # TODO
                        uk = uk[:, :max(uk.shape[1] - kickrank + 1, 1):-1]
                else:
                    uk = np.random.rand(ry[i] * n[i], kickrank)
                u, rv = np.linalg.qr(np.concatenate((u, uk), axis=1))
                radd = uk.shape[1]
            v = np.concatenate((v, np.zeros((ry[i + 1] * d2, radd))), axis=1)
            v = np.dot(rv, np.conj(np.transpose(v)))
            r = u.shape[1]
            
            cr2 = cry[i + 1]
            cr2 = reshape(cr2, (ry[i + 1], n[i + 1] * ry[i + 2]))
            v = reshape(v, (r * ry[i + 1], d2))
            v = reshape(np.transpose(v), (d2 * r, ry[i + 1]))
            v = np.dot(v, cr2)
            
            ry[i + 1] = r
            
            u = reshape(u, (ry[i], n[i], r))
            v = reshape(v, (d2, r, n[i + 1], ry[i + 2]))
            
            cry[i] = u
            cry[i + 1] = v
            
            Ry[i + 1] = np.dot(Ry[i], reshape(u, (ry[i], n[i] * ry[i + 1])))
            Ry[i + 1] = reshape(Ry[i + 1], (ry[i] * n[i], ry[i + 1]))
            curind = maxvol(Ry[i + 1])
            Ry[i + 1] = Ry[i + 1][curind, :]
            for j in range(nx):
                Rx[i + 1, j] = reshape(crx[i, j], (rx[i, j], n[i] * rx[i + 1, j]))
                Rx[i + 1, j] = np.dot(Rx[i, j], Rx[i + 1, j])
                Rx[i + 1, j] = reshape(Rx[i + 1, j], (ry[i] * n[i], rx[i + 1, j]))
                Rx[i + 1, j] = Rx[i + 1, j][curind, :]
        elif dirn < 0 and i > 0:
            u = np.dot(u[:, :r], np.diag(s[:r]))
            v = np.conj(v[:, :r])
            
            radd = 0
            rv = 1
            if not last_sweep and kickrank > 0:
                if kicktype == 'amr-two':
                    # compute the X superblocks
                    ind2 = np.unique(np.random.randint(0, ry[i - 1] * n[i - 1], ry[i]))
                    #ind2 = np.unique(np.floor(np.random.rand(ry[i]) * (ry[i - 1] * n[i - 1])))
                    rkick = len(ind2)
                    curbl = np.zeros((rkick * n[i] * ry[i + 1], nx))
                    for j in range(nx):
                        cr1 = reshape(crx[i, j], (rx[i, j] * n[i], rx[i + 1, j]))
                        cr1 = np.dot(cr1, Rx[i + 1, j])
                        cr1 = reshape(cr1, (rx[i, j], n[i] * ry[i + 1]))
                        cr2 = reshape(crx[i - 1, j], (rx[i - 1, j], n[i - 1] * rx[i, j]))
                        cr2 = np.dot(Rx[i - 1, j], cr2)
                        cr2 = reshape(cr2, (ry[i - 1] * n[i - 1], rx[i, j]))
                        cr2 = cr2[ind2, :]
                        curbl[:, j] = reshape(np.dot(cr2, cr1), (rkick * n[i] * ry[i + 1],))
                    # calling the function
                    uk = funs(curbl)
                    uk = reshape(uk, (rkick * n[i] * ry[i + 1], d2))
                    uk = reshape(np.transpose(uk), (d2 * rkick * n[i], ry[i + 1]))
                    uk = np.transpose(np.linalg.solve(np.transpose(Ry[i + 1]), np.transpose(uk)))
                    uk = reshape(uk, (d2 * rkick, n[i] * ry[i + 1]))
                    if pcatype == 'svd':
                        vk, sk, uk = np.linalg.svd(uk, full_matrices=False)
                        uk = np.transpose(uk)
                        uk = uk[:, :min(kickrank, uk.shape[1])] # TODO: refactor
                    else:
                        # uk = uchol(uk, kickrank + 1) # TODO
                        uk = uk[:, :max(uk.shape[1] - kickrank + 1, 1):-1]
                else:
                    uk = np.random.rand(n[i] * ry[i + 1], kickrank)
                v, rv = np.linalg.qr(np.concatenate((v, uk), axis=1))
                radd = uk.shape[1]
            u = np.concatenate((u, np.zeros((d2 * ry[i], radd))), axis=1)
            u = np.dot(u, np.transpose(rv))
            r = v.shape[1]
            cr2 = cry[i - 1]
            cr2 = reshape(cr2, (ry[i - 1] * n[i - 1], ry[i]))
            u = reshape(u, (d2, ry[i] * r))
            u = reshape(np.transpose(u), (ry[i], r * d2))
            u = np.dot(cr2, u)
            
            u = reshape(u, (ry[i - 1] * n[i - 1] * r, d2))
            u = reshape(np.transpose(u), (d2, ry[i - 1], n[i - 1], r))
            v = reshape(np.transpose(v), (r, n[i], ry[i + 1]))
            
            ry[i] = r
            cry[i - 1] = u
            cry[i] = v
            
            Ry[i] = np.dot(reshape(v, (ry[i] * n[i], ry[i + 1])), Ry[i + 1])
            Ry[i] = reshape(Ry[i], (ry[i], n[i] * ry[i + 1]))
            curind = maxvol(np.transpose(Ry[i]))
            Ry[i] = Ry[i][:, curind]
            for j in range(nx):
                Rx[i, j] = reshape(crx[i, j], (rx[i, j] * n[i], rx[i + 1, j]))
                Rx[i, j] = np.dot(Rx[i, j], Rx[i + 1, j])
                Rx[i, j] = reshape(Rx[i, j], (rx[i, j], n[i] * ry[i + 1]))
                Rx[i, j] = Rx[i, j][:, curind]
        elif dirn > 0 and i == d - 1:
            newy = np.dot(np.dot(u[:, :r], np.diag(s[:r])), np.conj(np.transpose(v[:, :r])))
            newy = reshape(newy, (ry[i] * n[i] * ry[i + 1], d2))
            cry[i] = reshape(np.transpose(newy), (d2, ry[i], n[i], ry[i + 1]))
        elif dirn < 0 and i == 0:
            newy = np.dot(np.dot(u[:, :r], np.diag(s[:r])), np.conj(np.transpose(v[:, :r])))
            newy = reshape(newy, (d2, ry[i], n[i], ry[i + 1]))
            cry[i] = newy
        
        #import ipdb; ipdb.set_trace() 
        i = i + dirn
        cur_order[order_index] = cur_order[order_index] - dirn
        if cur_order[order_index] == 0:
            order_index = order_index + 1
            if verb > 0:
                print '=multifuncrs= sweep %d{%d}, max_dy: %3.3e, erank: %g\n' % (swp, order_index, max_dy, \
                    math.sqrt(np.dot(ry[:d], n * ry[1:]) / np.sum(n)))
            
            if last_sweep:
                 break
            if max_dy < eps and dirn < 0:
                last_sweep = True
                kickrank = 0
            
            #import ipdb; ipdb.set_trace();
            
            if order_index >= len(cur_order):
                cur_order = copy.copy(block_order)
                order_index = 0
                if last_sweep:
                    cur_order = [d - 1]
                
                max_dy = 0
                swp = swp + 1
            
            dirn = int(math.copysign(1, cur_order[order_index]))
            i = i + dirn
            
        
    cry[d - 1] = np.transpose(cry[d - 1][:, :, :, 0], [1, 2, 0])
    y = tt.tensor.from_list(cry)
    return y
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    