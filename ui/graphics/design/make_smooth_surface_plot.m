clear variables;
clc;
close all;


f = figure;
set(f, 'color', '#302f2f');
set(f, 'Units', 'pixels');
set(f, 'Position', [0 0 600 600]);

[x, y] = meshgrid(-1:0.25:1, -1:0.25:1);
z = -x.^2/5 - y.^2;
surf(z, 'EdgeColor', 'white', 'LineWidth', 3, 'FaceAlpha', 0);
% xlim([-1 1]);
% ylim([-1 1]);
zlim([-1.5 1.5]);
view(-70, 40);

% z = peaks(1000);
% surf(z, 'EdgeColor', 'none');
% xlim([150 750]);
% ylim([150 750]);
% zlim([-15 15]);

grid off;
axis off;

imwrite(getframe(f).cdata, 'smooth_surface_grid.png');