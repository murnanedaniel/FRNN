import glob
import csv

import torch
import frnn
from pytorch3d.ops.knn import knn_points

num_points_fixed_query = 100000


class TestFRNN:

    def __init__(self, num_pcs=1, K=5, r=1.0, D=4):
        pc1 = torch.rand((num_pcs, num_points_fixed_query, D),
                         dtype=torch.float)
        pc2 = torch.rand((num_pcs, num_points_fixed_query, D),
                         dtype=torch.float)

        self.D = D
        self.num_pcs = num_pcs
        self.K = K
        self.r = r
        num_points = pc2.shape[1]
        self.num_points = num_points
        self.pc1_knn = pc1.clone().detach().cuda()
        self.pc2_knn = pc2.clone().detach().cuda()
        self.pc1_frnn = pc1.clone().detach().cuda()
        self.pc2_frnn = pc2.clone().detach().cuda()
        self.pc1_frnn_reuse = pc1.clone().detach().cuda()
        self.pc2_frnn_reuse = pc2.clone().detach().cuda()
        # self.pc1_knn.requires_grad_(True)
        # self.pc2_knn.requires_grad_(True)
        # self.pc1_frnn.requires_grad_(True)
        # self.pc2_frnn.requires_grad_(True)
        # self.pc1_frnn_reuse.requires_grad_(True)
        # self.pc2_frnn_reuse.requires_grad_(True)
        lengths1 = torch.ones(
            (num_pcs,), dtype=torch.long) * num_points_fixed_query
        lengths2 = torch.ones(
            (num_pcs,), dtype=torch.long) * num_points_fixed_query
        self.lengths1_cuda = lengths1.cuda()
        self.lengths2_cuda = lengths2.cuda()
        self.grid = None
        # self.grad_dists = torch.ones((num_pcs, pc1.shape[0], K), dtype=torch.float32).cuda()

    def frnn_grid(self):
        dists, idxs, nn, grid = frnn.frnn_grid_points(self.pc1_frnn,
                                                      self.pc2_frnn,
                                                      self.lengths1_cuda,
                                                      self.lengths2_cuda,
                                                      K=self.K,
                                                      r=self.r,
                                                      grid=None,
                                                      return_nn=True,
                                                      return_sorted=True)
        if self.grid is None:
            self.grid = grid
        return dists, idxs, nn

    def frnn_grid_reuse(self):
        dists, idxs, nn, _ = frnn.frnn_grid_points(self.pc1_frnn_reuse,
                                                   self.pc2_frnn_reuse,
                                                   self.lengths1_cuda,
                                                   self.lengths2_cuda,
                                                   K=self.K,
                                                   r=self.r,
                                                   grid=self.grid,
                                                   return_nn=True,
                                                   return_sorted=True)
        return dists, idxs, nn

    def knn(self):
        dists, idxs, nn = knn_points(self.pc1_knn,
                                     self.pc2_knn,
                                     self.lengths1_cuda,
                                     self.lengths2_cuda,
                                     K=self.K,
                                     version=-1,
                                     return_nn=True,
                                     return_sorted=True)
        # for backward, assume all we have k neighbors within the radius
        # mask = dists > self.r * self.r
        # idxs[mask] = -1
        # dists[mask] = -1
        # nn[mask] = 0.
        return dists, idxs, nn

    def frnn_bf(self):
        idxs, dists = frnn._C.frnn_bf_cuda(self.pc1_cuda, self.pc2_cuda,
                                           self.lengths1_cuda,
                                           self.lengths2_cuda, self.K, self.r)
        return dists, idxs

    def compare_frnn_knn(self):
        # forward
        dists_knn, idxs_knn, nn_knn = self.knn()
        dists_frnn, idxs_frnn, nn_frnn = self.frnn_grid()
        dists_frnn_reuse, idxs_frnn_reuse, nn_frnn_reuse = self.frnn_grid_reuse(
        )

        # modify results from knn to make it match frnn
        mask = idxs_frnn == -1
        idxs_knn[mask] = -1
        dists_knn[mask] == dists_frnn[mask]
        nn_knn[mask[...,
                    None].expand(-1, -1, -1,
                                 self.D)] = nn_frnn[mask[..., None].expand(
                                     -1, -1, -1, self.D)]
        # print(dists_knn)
        # print(dists_frnn)

        # dists_frnn_bf, idxs_frnn_bf = self.frnn_bf()

        # backward
        # loss_knn = (dists_knn * self.grad_dists).sum()
        # loss_knn.backward()
        # loss_frnn = (dists_frnn * self.grad_dists).sum()
        # loss_frnn.backward()
        # loss_frnn_reuse = (dists_frnn_reuse * self.grad_dists).sum()
        # loss_frnn_reuse.backward()

        idxs_all_same = torch.all(idxs_frnn == idxs_knn).item()
        idxs_all_same_reuse = torch.all(idxs_frnn_reuse == idxs_knn).item()
        diff_keys_percentage = torch.sum(idxs_frnn == idxs_knn).type(
            torch.float).item() / self.K / self.pc1_knn.shape[1] / self.num_pcs
        diff_keys_percentage_reuse = torch.sum(
            idxs_frnn_reuse == idxs_knn).type(torch.float).item(
            ) / self.K / self.pc1_knn.shape[1] / self.num_pcs
        dists_all_close = torch.allclose(dists_frnn, dists_knn)
        dists_all_close_reuse = torch.allclose(dists_frnn_reuse, dists_knn)
        return [
            self.D, idxs_all_same, f"{diff_keys_percentage:.16f}",
            dists_all_close, idxs_all_same_reuse,
            f"{diff_keys_percentage_reuse:.16f}", dists_all_close_reuse
        ]
        # pc1_grad_all_close = torch.allclose(self.pc1_frnn.grad, self.pc1_knn.grad, atol=5e-6)
        # # pc1_grad_all_close_reuse = torch.allclose(self.pc1_frnn_reuse.grad, self.pc1_knn.grad)
        # pc1_grad_all_close_reuse = True
        # pc2_grad_all_close = torch.allclose(self.pc2_frnn.grad, self.pc2_knn.grad, atol=5e-6)
        # # pc2_grad_all_close_reuse = torch.allclose(self.pc2_frnn_reuse.grad, self.pc2_knn.grad)
        # pc2_grad_all_close_reuse = True
        # return [self.fname, self.num_points, idxs_all_same, idxs_all_same_reuse,
        #         "{:.4f}".format(diff_keys_percentage), "{:.4f}".format(diff_keys_percentage_reuse),
        #         dists_all_close, dists_all_close_reuse, nn_all_close, nn_all_close_reuse, pc1_grad_all_close,
        #         pc1_grad_all_close_reuse, pc2_grad_all_close, pc2_grad_all_close_reuse]


if __name__ == "__main__":
    with open("tests/output/frnn_validation_ND.csv", 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'Dim', 'Different key percentage', 'Dists all close',
            'Different key percentage reuse', 'Dists all close reuse'
        ])
        for d in range(4, 9):
            for k in range(14, 65, 10):
                validator = TestFRNN(D=d, K=k)
                results = validator.compare_frnn_knn()
                print(d, k, results)
                writer.writerow(results)
            # results = validator.compare_frnnreuse_knn()
            # print(results)
            # writer.writerow(results)
